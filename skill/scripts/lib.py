"""Shared helpers for the claude-code-freeagent skill.

Self-contained: talks to FreeAgent + Gmail via LOCAL OAuth tokens and the Python stdlib only
(no MCPs), so the same code works interactively AND headless/scheduled.

CONFIG (nothing personal is hard-coded — see config.example.json):
  Looked up in this order:
    1. $CLAUDE_FREEAGENT_CONFIG
    2. ~/.config/claude-code-freeagent/config.json
    3. <repo>/config.json  (two levels up from this file)
  It provides the credential-file paths, the Downloads dir, the audit-trail marker, and any
  per-account date cutoffs. Bank accounts themselves are DISCOVERED from the API — never hard-coded.

CREDENTIALS live in the env files named by config (chmod 600, OUTSIDE any git repo). They are
never read from, or written to, this repository.
"""
import os, json, base64, re, urllib.request, urllib.parse, urllib.error

_DEFAULTS = {
    "freeagent_credentials": "~/.config/claude-code-freeagent/freeagent.env",
    "gmail_credentials": "~/.config/claude-code-freeagent/gmail.env",
    "downloads_dir": "~/Downloads",
    "cc_marker": "(CC)",
    "account_cutoffs": {},
}


def _load_config():
    candidates = [
        os.environ.get("CLAUDE_FREEAGENT_CONFIG"),
        os.path.expanduser("~/.config/claude-code-freeagent/config.json"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "config.json"),
    ]
    cfg = dict(_DEFAULTS)
    for c in candidates:
        if c and os.path.exists(c):
            cfg.update(json.load(open(c)))
            break
    return cfg


_CFG = _load_config()
FA_ENV = os.path.expanduser(_CFG["freeagent_credentials"])
GM_ENV = os.path.expanduser(_CFG["gmail_credentials"])
DOWNLOADS = os.path.expanduser(_CFG["downloads_dir"])
CC_MARKER = _CFG.get("cc_marker", "(CC)")
_CUTOFFS = _CFG.get("account_cutoffs", {})


def account_start(name):
    """Earliest date (ISO string) we care about for a given account name, or None.
    Some connected accounts import pre-business history (e.g. a personal account linked mid-year);
    set a cutoff in config.account_cutoffs to ignore anything on that account before that date."""
    return _CUTOFFS.get(name)


def load_env(path):
    if not os.path.exists(path):
        raise SystemExit(
            f"Credential file not found: {path}\n"
            "Run the one-time setup first (docs/SETUP.md in the repo), or ask Claude to set it up.\n"
            "If your credentials live elsewhere, point config.json at them "
            "(~/.config/claude-code-freeagent/config.json).")
    env = {}
    for line in open(path):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k] = v.strip()
    return env


def _save_env_value(path, key, value):
    lines = open(path).read().splitlines()
    out, seen = [], False
    for l in lines:
        if l.startswith(key + '='):
            out.append(f'{key}={value}'); seen = True
        else:
            out.append(l)
    if not seen:
        out.append(f'{key}={value}')
    open(path, 'w').write('\n'.join(out) + '\n')


# ---------------- FreeAgent ----------------
def fa_refresh():
    """Refresh the FreeAgent access token and persist it. Tokens last ~1h."""
    e = load_env(FA_ENV)
    data = urllib.parse.urlencode({
        'grant_type': 'refresh_token', 'refresh_token': e['FREEAGENT_REFRESH_TOKEN'],
        'client_id': e['FREEAGENT_CLIENT_ID'], 'client_secret': e['FREEAGENT_CLIENT_SECRET']}).encode()
    with urllib.request.urlopen(urllib.request.Request(f"{e['FREEAGENT_BASE_URL']}/v2/token_endpoint", data=data)) as r:
        tok = json.load(r)['access_token']
    _save_env_value(FA_ENV, 'FREEAGENT_ACCESS_TOKEN', tok)
    return tok


def fa_api(path, method='GET', payload=None):
    """Call FreeAgent. Auto-refreshes once on 401 (expired token)."""
    e = load_env(FA_ENV)
    base, token = e['FREEAGENT_BASE_URL'], e.get('FREEAGENT_ACCESS_TOKEN', '')
    url = path if path.startswith('http') else f"{base}{path}"

    def _call(tok):
        data = json.dumps(payload).encode() if payload else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as r:
            body = r.read()  # DELETE returns 200/204 with an EMPTY body
            return r.status, (json.loads(body) if body.strip() else {})

    try:
        return _call(token)
    except urllib.error.HTTPError as ex:
        if ex.code == 401:
            return _call(fa_refresh())
        return ex.code, ex.read().decode()


def fa_get(path):
    """GET that fails loudly with a readable message instead of handing callers an error string
    (a raw AttributeError on `.get()` is how a bad token once surfaced as a confusing crash)."""
    st, d = fa_api(path)
    if not isinstance(d, dict):
        raise SystemExit(f"FreeAgent API error {st} for {path.split('?')[0]}: {str(d)[:300]}")
    return d


def fa_get_explanation(eid):
    return fa_get(f"/v2/bank_transaction_explanations/{eid}").get('bank_transaction_explanation', {})


def get_accounts():
    """Discover the business's bank accounts from FreeAgent → {name: id}. Never hard-coded, so
    this works for any account without configuring IDs."""
    d = fa_get("/v2/bank_accounts")
    return {a.get('name'): int(a.get('url').split('/')[-1]) for a in d.get('bank_accounts', [])}


def mime_for(path):
    """Content type for a receipt file — FreeAgent accepts PDF/PNG/JPEG/GIF, and a photo receipt
    is a first-class citizen here, so don't mislabel a .jpg as a PDF. Unsupported types (e.g. an
    iPhone .heic) fail loudly rather than upload with a wrong label — convert those first."""
    ext = os.path.splitext(path)[1].lower()
    m = {'.pdf': 'application/pdf', '.png': 'image/png', '.jpg': 'image/jpeg',
         '.jpeg': 'image/jpeg', '.gif': 'image/gif'}.get(ext)
    if not m:
        raise SystemExit(f"Unsupported attachment type '{ext}' ({os.path.basename(path)}). "
                         "FreeAgent accepts PDF/PNG/JPEG/GIF — convert it first "
                         "(e.g. on macOS: sips -s format jpeg in.heic --out out.jpg).")
    return m


# ---------------- Gmail (read-only) ----------------
def gm_refresh():
    e = load_env(GM_ENV)
    data = urllib.parse.urlencode({
        'grant_type': 'refresh_token', 'refresh_token': e['GMAIL_REFRESH_TOKEN'],
        'client_id': e['GMAIL_CLIENT_ID'], 'client_secret': e['GMAIL_CLIENT_SECRET']}).encode()
    with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=data)) as r:
        tok = json.load(r)['access_token']
    _save_env_value(GM_ENV, 'GMAIL_ACCESS_TOKEN', tok)
    return tok


def gm_api(url):
    e = load_env(GM_ENV)

    def _call(tok):
        req = urllib.request.Request(url, headers={'Authorization': f'Bearer {tok}'})
        with urllib.request.urlopen(req) as r:
            return json.load(r)

    try:
        return _call(e.get('GMAIL_ACCESS_TOKEN', ''))
    except urllib.error.HTTPError as ex:
        if ex.code == 401:
            return _call(gm_refresh())
        raise


def gm_search(query, max_results=10):
    q = urllib.parse.quote(query)
    d = gm_api(f"https://gmail.googleapis.com/gmail/v1/users/me/messages?q={q}&maxResults={max_results}")
    return [m['id'] for m in d.get('messages', [])]


def gm_message(msgid):
    return gm_api(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msgid}?format=full")


def gm_body_text(msg):
    acc = []

    def walk(p):
        b = p.get('body', {})
        if b.get('data'):
            try:
                acc.append(base64.urlsafe_b64decode(b['data']).decode('utf-8', 'ignore'))
            except Exception:
                pass
        for sp in p.get('parts', []) or []:
            walk(sp)
    walk(msg['payload'])
    return ' '.join(acc)


def gm_find_pdf_attachment(msg, prefer=None):
    cands = []

    def walk(parts):
        for p in parts or []:
            fn = p.get('filename') or ''
            if fn.lower().endswith('.pdf') and p.get('body', {}).get('attachmentId'):
                cands.append((fn, p['body']['attachmentId']))
            walk(p.get('parts'))
    walk(msg['payload'].get('parts'))
    if prefer:
        for fn, aid in cands:
            if prefer.lower() in fn.lower():
                return fn, aid
    return cands[0] if cands else None


def gm_download_attachment(msgid, attachment_id):
    d = gm_api(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msgid}/attachments/{attachment_id}")
    return base64.urlsafe_b64decode(d['data'])


def extract_stripe_pdf_links(body):
    urls = set(re.findall(r'https?://[^\s"\'<>)]+', body))
    pay = [u for u in urls if 'pay.stripe.com/invoice' in u and '/pdf' in u]
    dash = [u for u in urls if 'dashboard.stripe.com/receipts' in u and '/pdf' in u]
    return pay + dash


def http_download(url):
    return urllib.request.urlopen(urllib.request.Request(url)).read()


# ---------------- Downloads enumeration ----------------
def list_downloads_pdfs():
    """Every PDF in the Downloads dir with size + mtime. Enumerate ALL of them and match by
    amount/period — do NOT rely on a name search (it can silently miss a real invoice)."""
    import glob, time
    out = []
    for pat in ('*.pdf', '*.PDF'):
        for p in glob.glob(os.path.join(DOWNLOADS, '**', pat), recursive=True):
            st = os.stat(p)
            out.append({'path': p, 'name': os.path.basename(p), 'kb': st.st_size // 1024,
                        'mtime': time.strftime('%Y-%m-%d', time.localtime(st.st_mtime))})
    return sorted(out, key=lambda x: x['mtime'], reverse=True)
