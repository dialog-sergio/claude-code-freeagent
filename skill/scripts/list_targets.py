"""List bank transactions that need work, so nothing is missed.

Two buckets:
  UNEXPLAINED       - no explanation yet (need full explain + invoice)
  MISSING_INVOICE   - explained money-out with no attachment (need the PDF)

Usage:
  python list_targets.py --from 2026-01-01 --to 2026-06-30 [--account "Account Name"] [--json out.json]
"""
import sys, os, json, argparse, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import fa_api, fa_refresh, get_accounts, account_start, load_env, FA_ENV  # noqa: E402


def category_map():
    _, d = fa_api("/v2/categories")
    m = {}
    for grp in d.values():
        if isinstance(grp, list):
            for c in grp:
                if isinstance(c, dict) and c.get('url'):
                    m[c['url']] = c.get('description')
    return m


BASE = load_env(FA_ENV)['FREEAGENT_BASE_URL']


def paged_explanations(acc_id, frm, to):
    out, page = [], 1
    while True:
        q = urllib.parse.urlencode({'bank_account': f"{BASE}/v2/bank_accounts/{acc_id}",
                                    'from_date': frm, 'to_date': to, 'per_page': 100, 'page': page})
        _, d = fa_api(f"/v2/bank_transaction_explanations?{q}")
        exps = d.get('bank_transaction_explanations', [])
        if not exps:
            break
        out += exps
        if len(exps) < 100:
            break
        page += 1
    return out


def unexplained(acc_id, frm, to):
    base = BASE
    out, page = [], 1
    while True:
        q = urllib.parse.urlencode({'bank_account': f"{base}/v2/bank_accounts/{acc_id}",
                                    'view': 'unexplained', 'from_date': frm, 'to_date': to, 'per_page': 100, 'page': page})
        _, d = fa_api(f"/v2/bank_transactions?{q}")
        txns = d.get('bank_transactions', [])
        if not txns:
            break
        out += [t for t in txns if float(t.get('unexplained_amount') or 0) != 0]
        if len(txns) < 100:
            break
        page += 1
    return out


def for_review(acc_id, frm, to):
    """Transactions auto-explained by a bank rule/guess, pending approval (marked_for_review)."""
    out, page = [], 1
    while True:
        q = urllib.parse.urlencode({'bank_account': f"{BASE}/v2/bank_accounts/{acc_id}",
                                    'view': 'marked_for_review', 'from_date': frm, 'to_date': to,
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
    ap.add_argument('--from', dest='frm', required=True)
    ap.add_argument('--to', dest='to', required=True)
    ap.add_argument('--account', default=None, help='exact FreeAgent account name (from get_accounts); default all')
    ap.add_argument('--json', default=None)
    a = ap.parse_args()
    fa_refresh()  # start fresh
    cats = category_map()
    all_accts = get_accounts()
    accts = {a.account: all_accts[a.account]} if a.account else all_accts

    result = {'unexplained': [], 'for_approval': [], 'missing_invoice': []}
    for name, aid in accts.items():
        # Personal/late-linked accounts (e.g. Wise-UK) only count from their cutoff date on.
        acc_frm = max(a.frm, account_start(name)) if account_start(name) else a.frm
        for t in unexplained(aid, acc_frm, a.to):
            if (t.get('dated_on') or '') < acc_frm:
                continue
            result['unexplained'].append({'account': name, 'dated_on': t.get('dated_on'),
                'amount': t.get('amount'), 'description': t.get('description'),
                'url': t.get('url')})
        for t in for_review(aid, acc_frm, a.to):
            if (t.get('dated_on') or '') < acc_frm:
                continue
            result['for_approval'].append({'account': name, 'dated_on': t.get('dated_on'),
                'amount': t.get('amount'), 'description': t.get('description'),
                'url': t.get('url')})
        for e in paged_explanations(aid, acc_frm, a.to):
            if (e.get('dated_on') or '') < acc_frm:
                continue
            if float(e.get('gross_value') or 0) < 0 and not e.get('attachment'):
                result['missing_invoice'].append({'account': name, 'dated_on': e.get('dated_on'),
                    'amount': e.get('gross_value'), 'description': e.get('description'),
                    'category': cats.get(e.get('category'), e.get('category')),
                    'ec_status': e.get('ec_status'), 'eid': e.get('url', '').split('/')[-1]})

    print(f"UNEXPLAINED: {len(result['unexplained'])}")
    for t in sorted(result['unexplained'], key=lambda x: x['dated_on']):
        print(f"  {t['dated_on']} | {float(t['amount']):9.2f} | {t['account']:9} | {(t['description'] or '')[:50]}")
    print(f"\nFOR APPROVAL (auto-explained by a rule, awaiting approval): {len(result['for_approval'])}")
    for t in sorted(result['for_approval'], key=lambda x: x['dated_on']):
        print(f"  {t['dated_on']} | {float(t['amount']):9.2f} | {t['account']:9} | {(t['description'] or '')[:50]}")
    print(f"\nMISSING INVOICE (explained money-out, no attachment): {len(result['missing_invoice'])}")
    for e in sorted(result['missing_invoice'], key=lambda x: x['dated_on']):
        print(f"  {e['dated_on']} | {float(e['amount']):9.2f} | {e['ec_status']:13} | {e['category'][:20]:20} | {(e['description'] or '')[:38]}  #{e['eid']}")

    if a.json:
        json.dump(result, open(a.json, 'w'), indent=1)
        print(f"\nsaved -> {a.json}")


if __name__ == '__main__':
    main()
