"""Write to FreeAgent — RUN ONLY AFTER the user approves in chat.

Two modes:

  UPDATE an existing explanation (add invoice / set reverse charge):
    python attach.py --eid 742513705 --pdf /path/inv.pdf [--reverse-charge] [--note "..."]

  CREATE an explanation for an unexplained transaction (the going-forward case):
    python attach.py --bank-transaction <full url> --category-url <full url> \
        --gross -122.39 --dated-on 2026-07-07 --pdf /path/inv.pdf [--reverse-charge] [--note "..."]

Rules baked in:
  * Appends the audit-trail marker (from config, e.g. "(CC)") so you can see Claude touched it.
  * --reverse-charge sets ec_status="Reverse Charge" + sales_tax_rate="AUTO"
    (AUTO resolves to 0% for reverse charge — that is correct and expected).
  * Attaches the PDF (<=5MB; PDF/PNG/JPEG/GIF).
  * Prints BEFORE/AFTER so the write is verifiable.
"""
import sys, os, json, base64, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import fa_api, fa_get_explanation, CC_MARKER, mime_for  # noqa: E402


def with_cc(desc):
    """Tag the description with the audit-trail marker so touched transactions are filterable."""
    desc = desc or ''
    return desc if desc.endswith(CC_MARKER) else (f'{desc} {CC_MARKER}').strip()


def attachment_block(path, file_name, note_desc):
    """Works for PDFs and image receipts alike — content type inferred from the extension."""
    b64 = base64.b64encode(open(path, 'rb').read()).decode()
    return {"data": b64, "file_name": file_name or os.path.basename(path),
            "content_type": mime_for(path), "description": note_desc or "Supplier invoice"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--eid')
    ap.add_argument('--bank-transaction')
    ap.add_argument('--category-url')
    ap.add_argument('--gross', type=float)
    ap.add_argument('--dated-on')
    ap.add_argument('--pdf')
    ap.add_argument('--file-name')
    ap.add_argument('--reverse-charge', action='store_true')
    ap.add_argument('--vat-rate',
                    help='set sales_tax_rate explicitly, e.g. "0.0" for a zero-rated / no-reclaim '
                         'line (business gift or entertaining, exempt supply). Sets ec_status to '
                         'UK/Non-EC unless already set. Do NOT combine with --reverse-charge.')
    ap.add_argument('--manual-vat', type=float, default=None,
                    help='set an exact VAT amount (manual_sales_tax_amount) to match a receipt '
                         'whose stated VAT differs from a straight 20%% of gross (e.g. a mixed '
                         'zero-rated + standard-rated cafe bill). Pass the positive VAT figure.')
    ap.add_argument('--replace', action='store_true',
                    help='replace an EXISTING attachment. FreeAgent does NOT replace on PUT — '
                         'the old attachment must be DELETEd first, which this does. Only ever '
                         'replace after READING the existing file: a bank-named receipt (e.g. '
                         '"<bank>-Receipt-*.pdf") is '
                         'usually the real invoice you saved, not junk — do not blow it away.')
    ap.add_argument('--note', default=None, help='optional extra note text prepended before (CC)')
    ap.add_argument('--approve', action='store_true',
                    help='clear marked_for_review — i.e. approve a transaction a bank rule auto-'
                         'explained. Only after you have okayed the guessed category/VAT.')
    a = ap.parse_args()

    body = {}
    if a.pdf:
        body["attachment"] = attachment_block(a.pdf, a.file_name, a.note)
    if a.reverse_charge:
        body["ec_status"] = "Reverse Charge"
        body["sales_tax_rate"] = "AUTO"
    if a.vat_rate is not None:
        body["sales_tax_rate"] = a.vat_rate
        body.setdefault("ec_status", "UK/Non-EC")
    if a.manual_vat is not None:
        body["manual_sales_tax_amount"] = a.manual_vat
    if a.approve:
        body["marked_for_review"] = False

    if a.eid:  # UPDATE
        e = fa_get_explanation(a.eid)
        print("BEFORE: ec=%s rate=%s value=%s attach=%s desc=%r" % (
            e.get('ec_status'), e.get('sales_tax_rate'), e.get('sales_tax_value'),
            (e.get('attachment') or {}).get('file_name'), e.get('description')))
        existing = e.get('attachment') or {}
        if a.pdf and existing.get('url') and not a.replace:
            print(f"REFUSING: an attachment already exists ({existing.get('file_name')}). "
                  f"READ it first — it may be the real invoice. Re-run with --replace to delete + swap.")
            return
        if a.pdf and existing.get('url') and a.replace:
            st, _ = fa_api(existing['url'], 'DELETE')
            print(f"deleted existing attachment ({existing.get('file_name')}) status={st}")
        base_desc = e.get('description') or ''
        if a.note:
            base_desc = f"{base_desc} // {a.note}" if a.note not in base_desc else base_desc
        body["category"] = a.category_url or e.get('category')
        body["description"] = with_cc(base_desc)
        st, resp = fa_api(f"/v2/bank_transaction_explanations/{a.eid}", 'PUT',
                          {"bank_transaction_explanation": body})
        eid = a.eid
    else:      # CREATE
        assert a.bank_transaction and a.category_url and a.gross is not None and a.dated_on, \
            "create mode needs --bank-transaction --category-url --gross --dated-on"
        desc = with_cc(a.note or "")
        body.update({"bank_transaction": a.bank_transaction, "category": a.category_url,
                     "gross_value": a.gross, "dated_on": a.dated_on, "description": desc})
        st, resp = fa_api("/v2/bank_transaction_explanations", 'POST',
                          {"bank_transaction_explanation": body})
        eid = resp.get('bank_transaction_explanation', {}).get('url', '').split('/')[-1] if isinstance(resp, dict) else '?'

    print("WRITE status:", st)
    if isinstance(resp, str):
        print("ERROR:", resp[:600]); return
    e2 = fa_get_explanation(eid)
    att = e2.get('attachment') or {}
    print("AFTER:  ec=%s rate=%s value=%s attach=%s desc=%r" % (
        e2.get('ec_status'), e2.get('sales_tax_rate'), e2.get('sales_tax_value'),
        att.get('file_name'), e2.get('description')))


if __name__ == '__main__':
    main()
