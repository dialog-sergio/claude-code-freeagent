"""Back-audit: review EXISTING explanations across history, to sanity-check past bookkeeping.

This is the "did I do a good job on everything else?" pass you run once on install (and any time
you want a health check). It is READ-ONLY — it changes nothing. It surfaces things worth a second
look, which Claude then verifies by reading the actual invoices:

  1. money-out explanations with NO attachment (a missing receipt)
  2. reverse-charge explanations (Claude should verify EACH by reading the invoice — a supplier's
     web domain does not tell you the VAT treatment; a US-looking SaaS may be UK-VAT-registered)
  3. which VAT periods are already FILED, so any error found in one is flagged for the accountant
     rather than silently changed

Usage: python audit.py --from 2026-01-01 --to 2026-06-30 [--account "Account Name"] [--json report.json]
"""
import sys, os, json, argparse, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import fa_api, fa_refresh, get_accounts, account_start, load_env, FA_ENV  # noqa: E402

BASE = load_env(FA_ENV)['FREEAGENT_BASE_URL']

# Categories that legitimately never have a supplier invoice — don't flag these as "missing".
NON_INVOICE_HINTS = ('salar', 'wage', 'dividend', 'paye', 'national insurance', 'pension',
                     'corporation tax', 'vat', 'bank', 'transfer', 'loan', 'interest',
                     'drawings', 'director', 'trade creditor')


def category_map():
    _, d = fa_api("/v2/categories")
    m = {}
    for grp in d.values():
        if isinstance(grp, list):
            for c in grp:
                if isinstance(c, dict) and c.get('url'):
                    m[c['url']] = c.get('description')
    return m


def explanations(acc_id, frm, to):
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


def filed_periods():
    _, d = fa_api("/v2/vat_returns")
    out = []
    for v in d.get('vat_returns', []):
        out.append((v.get('period_starts_on'), v.get('period_ends_on'),
                    (v.get('filing_status') or ('filed' if v.get('filed_at') else 'open'))))
    return out


def in_filed_period(date, periods):
    for s, e, status in periods:
        if s and e and s <= (date or '') <= e and status == 'filed':
            return f"{s}..{e}"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--from', dest='frm', required=True)
    ap.add_argument('--to', dest='to', required=True)
    ap.add_argument('--account', default=None)
    ap.add_argument('--json', default=None)
    a = ap.parse_args()
    fa_refresh()
    cats = category_map()
    periods = filed_periods()
    all_accts = get_accounts()
    accts = {a.account: all_accts[a.account]} if a.account else all_accts

    missing, reverse_charge = [], []
    for name, aid in accts.items():
        acc_frm = max(a.frm, account_start(name)) if account_start(name) else a.frm
        for e in explanations(aid, acc_frm, a.to):
            if (e.get('dated_on') or '') < acc_frm:
                continue
            cat = cats.get(e.get('category'), e.get('category') or '')
            row = {'account': name, 'dated_on': e.get('dated_on'), 'amount': e.get('gross_value'),
                   'description': e.get('description'), 'category': cat, 'ec_status': e.get('ec_status'),
                   'filed_period': in_filed_period(e.get('dated_on'), periods),
                   'eid': (e.get('url') or '').split('/')[-1]}
            if float(e.get('gross_value') or 0) < 0 and not e.get('attachment') \
                    and not any(h in cat.lower() for h in NON_INVOICE_HINTS):
                missing.append(row)
            if e.get('ec_status') == 'Reverse Charge':
                reverse_charge.append(row)

    print(f"BACK-AUDIT {a.frm}..{a.to}\n")
    print(f"1) MONEY-OUT MISSING A RECEIPT: {len(missing)}")
    for r in sorted(missing, key=lambda x: x['dated_on']):
        print(f"   {r['dated_on']} | {float(r['amount']):9.2f} | {r['account']:18} | {r['category'][:18]:18} | {(r['description'] or '')[:32]}")
    print(f"\n2) REVERSE-CHARGE — VERIFY EACH BY READING THE INVOICE: {len(reverse_charge)}")
    print("   (a supplier's .com domain does NOT decide VAT treatment — only the invoice does)")
    for r in sorted(reverse_charge, key=lambda x: x['dated_on']):
        fp = f" [FILED {r['filed_period']}]" if r['filed_period'] else ""
        print(f"   {r['dated_on']} | {float(r['amount']):9.2f} | {(r['description'] or '')[:34]}{fp}")
    print("\n3) FILED VAT PERIODS (errors found in these = FLAG for accountant, do not change):")
    for s, e, status in periods:
        print(f"   {s}..{e}  [{status}]")

    if a.json:
        json.dump({'missing_receipt': missing, 'reverse_charge': reverse_charge,
                   'vat_periods': periods}, open(a.json, 'w'), indent=1)
        print(f"\nsaved -> {a.json}")
    print("\nNext: Claude reads each reverse-charge invoice to confirm the VAT treatment, and finds"
          " the missing receipts — then presents anything wrong for your approval (or, if it's in a"
          " filed period, flags it for your accountant).")


if __name__ == '__main__':
    main()
