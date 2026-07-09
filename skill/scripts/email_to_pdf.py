"""Render an email whose receipt lives in the BODY (no PDF attachment, no hosted link) into a
PDF so it can be attached in FreeAgent.

The classic case is **Trainline booking confirmations**: the journey, price and VAT are HTML in
the email body, and the only PDF Trainline sends is the e-ticket (not a priced receipt). This
turns the confirmation email itself into the receipt document.

Uses Chrome headless, which renders faithfully WITHOUT a display — so it is schedule-safe.

Usage:
  python email_to_pdf.py <gmail_msgid> <outpath.pdf>
"""
import sys, os, base64, subprocess, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import gm_message  # noqa: E402

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def html_body(msg):
    htmls = []

    def walk(p):
        if p.get('mimeType') == 'text/html' and p.get('body', {}).get('data'):
            htmls.append(base64.urlsafe_b64decode(p['body']['data']).decode('utf-8', 'ignore'))
        for sp in p.get('parts', []) or []:
            walk(sp)
    walk(msg['payload'])
    return '\n'.join(htmls)


def render(msgid, out):
    m = gm_message(msgid)
    html = html_body(m)
    if not html:
        raise RuntimeError("no HTML body found in this message")
    tmp = tempfile.mkdtemp()
    htmlpath = os.path.join(tmp, "email.html")
    open(htmlpath, 'w', encoding='utf-8').write(html)
    if os.path.exists(out):
        os.remove(out)
    cmd = [CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
           f"--user-data-dir={os.path.join(tmp, 'profile')}",
           "--virtual-time-budget=6000",
           f"--print-to-pdf={out}", f"file://{htmlpath}"]
    # Chrome writes the PDF then sometimes hangs on teardown (remote images / tracking pixels).
    # We don't care about a clean exit — kill it after a short wait and use the file if it landed.
    try:
        subprocess.run(cmd, capture_output=True, timeout=25)
    except subprocess.TimeoutExpired:
        pass
    if not (os.path.exists(out) and os.path.getsize(out) > 1000):
        raise RuntimeError("Chrome render produced no usable PDF")
    return os.path.getsize(out)


if __name__ == '__main__':
    size = render(sys.argv[1], sys.argv[2])
    print(f"rendered -> {sys.argv[2]} ({size} bytes)")
