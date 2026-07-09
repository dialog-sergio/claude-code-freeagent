"""Toolbox for locating an invoice PDF for a transaction, across all three sources.

The MATCHING (by period/amount/supplier) and the reverse-charge decision are done by
you (the model) after reading the PDF — these commands just fetch candidates.

Commands:
  downloads
      List every PDF in ~/Downloads (name | KB | date). Enumerate ALL and match by
      amount/period — never trust a supplier-name search alone (it has missed real invoices).

  gmail-search "<gmail query>"
      Search Gmail (via the local API). Prints msgid | date | subject and whether the
      message has a PDF attachment and/or a Stripe hosted-invoice link.
      Example query: 'from:mail.anthropic.com receipt after:2026/03/10 before:2026/03/25'

  gmail-fetch <msgid> <outpath> [prefer_name_substring]
      Download the invoice PDF from a message to <outpath>. Tries a real PDF attachment
      first (preferring the name substring, e.g. "Invoice" over "Receipt"), then falls
      back to a Stripe hosted-invoice link in the body.

  stripe-fetch <url> <outpath>
      Download a public Stripe/hosted PDF link directly.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import (list_downloads_pdfs, gm_search, gm_message, gm_body_text,  # noqa: E402
                 gm_find_pdf_attachment, gm_download_attachment, extract_stripe_pdf_links, http_download)


def cmd_downloads():
    for f in list_downloads_pdfs():
        print(f"{f['mtime']} | {f['kb']:6d}KB | {f['name']}")


def cmd_gmail_search(query):
    ids = gm_search(query, max_results=10)
    if not ids:
        print("(no matches)")
        return
    for mid in ids:
        m = gm_message(mid)
        hdrs = {h['name']: h['value'] for h in m['payload'].get('headers', [])}
        att = gm_find_pdf_attachment(m)
        links = extract_stripe_pdf_links(gm_body_text(m))
        flags = []
        if att:
            flags.append(f"pdf-attach:{att[0]}")
        if links:
            flags.append("stripe-link")
        print(f"{mid} | {hdrs.get('Date','?')[:16]} | {hdrs.get('Subject','')[:55]} | {' '.join(flags) or 'no-pdf'}")


def cmd_gmail_fetch(msgid, outpath, prefer=None):
    m = gm_message(msgid)
    att = gm_find_pdf_attachment(m, prefer)
    if att:
        raw = gm_download_attachment(msgid, att[1])
        open(outpath, 'wb').write(raw)
        print(f"downloaded attachment {att[0]} ({len(raw)} bytes) -> {outpath}")
        return
    links = extract_stripe_pdf_links(gm_body_text(m))
    if links:
        raw = http_download(links[0])
        open(outpath, 'wb').write(raw)
        print(f"downloaded stripe link ({len(raw)} bytes) -> {outpath}")
        return
    print("no PDF attachment or stripe link found in this message")


def cmd_stripe_fetch(url, outpath):
    raw = http_download(url)
    open(outpath, 'wb').write(raw)
    print(f"downloaded ({len(raw)} bytes) -> {outpath}")


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'downloads':
        cmd_downloads()
    elif cmd == 'gmail-search':
        cmd_gmail_search(sys.argv[2])
    elif cmd == 'gmail-fetch':
        cmd_gmail_fetch(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    elif cmd == 'stripe-fetch':
        cmd_stripe_fetch(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
