"""Lightweight watcher: are there bank transactions in FreeAgent that need attention?

TWO states need your attention (both must be checked — checking only one misses work):
  UNEXPLAINED   - no explanation at all yet.
  FOR-APPROVAL  - auto-explained by a bank rule/guess (`marked_for_review`), pending your
                  approval. These have unexplained_amount == 0, so an "unexplained-only" check
                  is blind to them — which is exactly how one got missed.

Cheap + read-only — safe to run on a schedule. Prints a one-line summary and a short list,
and exits 1 if there is anything to do (0 if all clear), so a scheduler can branch on it.

Usage: python check_unexplained.py [--days 180]
"""
import sys, os, argparse, urllib.parse, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import fa_api, fa_refresh, get_accounts, load_env, FA_ENV, account_start  # noqa: E402

BASE = load_env(FA_ENV)['FREEAGENT_BASE_URL']


def _txns(acc_id, view, frm, to):
    out, page = [], 1
    while True:
        q = urllib.parse.urlencode({'bank_account': f"{BASE}/v2/bank_accounts/{acc_id}",
                                    'view': view, 'from_date': frm, 'to_date': to,
                                    'per_page': 100, 'page': page})
        _, d = fa_api(f"/v2/bank_transactions?{q}")
        txns = d.get('bank_transactions', [])
        if not txns:
            break
        out += txns
        if len(txns) < 100:
            break
        page += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=180, help='look-back window (days)')
    a = ap.parse_args()
    fa_refresh()
    today = datetime.date.today()
    frm = (today - datetime.timedelta(days=a.days)).isoformat()
    to = today.isoformat()

    found = []  # (state, account, date, amount, desc)
    for name, aid in get_accounts().items():
        # Personal/late-linked accounts (e.g. Wise-UK) only count from their cutoff date onwards.
        acc_frm = max(frm, account_start(name)) if account_start(name) else frm
        for t in _txns(aid, 'unexplained', acc_frm, to):
            if float(t.get('unexplained_amount') or 0) == 0 or (t.get('dated_on') or '') < acc_frm:
                continue
            found.append(('unexplained', name, t.get('dated_on'), t.get('amount'), t.get('description')))
        for t in _txns(aid, 'marked_for_review', acc_frm, to):
            if (t.get('dated_on') or '') < acc_frm:
                continue
            found.append(('for-approval', name, t.get('dated_on'), t.get('amount'), t.get('description')))

    if not found:
        print(f"CLEAR: nothing needs attention in the last {a.days} days.")
        sys.exit(0)

    found.sort(key=lambda x: x[2] or '')
    ux = sum(1 for f in found if f[0] == 'unexplained')
    fa = sum(1 for f in found if f[0] == 'for-approval')
    print(f"WORK: {len(found)} transaction(s) need attention ({ux} unexplained, {fa} for-approval):")
    for state, name, d, amt, desc in found:
        print(f"  [{state:12}] {d} | {float(amt):9.2f} | {name:9} | {(desc or '')[:45]}")
    sys.exit(1)


if __name__ == '__main__':
    main()
