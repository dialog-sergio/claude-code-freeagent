# For your accountant

A plain-English brief on how this tool interacts with the FreeAgent books, the controls around it,
and the VAT methodology — so you can assess it. Nothing here is automated tax advice; a human
approves every change.

## What it is

A [Claude Code](https://claude.com/claude-code) assistant that helps the business owner **explain
and document bank transactions in FreeAgent**. It finds each transaction's invoice/receipt, works
out the VAT treatment by reading the actual invoice, and prepares the entry — but it **only writes
to the books after the owner explicitly approves each one in chat.**

## The controls you'll care about

1. **Nothing is written without human approval.** Every attachment, category, VAT setting, and
   approval is presented to the owner first (supplier, amount, matched invoice, VAT treatment, and
   the exact change). Only on their "approve" does it write. There is no silent/auto-posting mode.
2. **Full audit trail.** Every transaction the assistant touches gets a marker appended to its
   description (by default `(CC)`). **You can filter/search FreeAgent for that marker** to see
   precisely what was assistant-assisted versus hand-entered.
3. **Filed VAT periods are never altered.** If the tool finds a VAT error in a period whose return
   is already **filed**, it does **not** change it — it flags it (supplier, date, amount, the error,
   the VAT quarter) for you to correct through the proper channel (typically an adjustment on the
   next return). It only edits current/open-period entries, and only with approval.
4. **Least-privilege access.** FreeAgent access is the owner's own OAuth app. Email access (used
   only to retrieve invoices) is **read-only** — it cannot send or delete. Credentials are stored
   locally on the owner's machine, never in any shared repository.

## VAT methodology (how it decides)

The core rule is **read the invoice; never infer VAT from the vendor's name or web domain.**

| The invoice shows… | Recorded as |
|---|---|
| Non-UK supplier, 0% / no VAT (often stated "reverse charge") | **Reverse charge** (`ec_status = Reverse Charge`, rate resolves to 0%; the notional 20% posts to Boxes 1 & 4, net-zero) |
| Any supplier that **charged UK VAT** (a GB VAT line at 20%/5%) | **Standard UK purchase**, input VAT reclaimed |
| UK supplier, no VAT (exempt / zero-rated, e.g. UK rail) | **Domestic**, no reclaim |

Notes we've found matter in practice:
- **A `.com` domain proves nothing.** Several well-known "US" SaaS vendors operate UK entities and
  charge 20% UK VAT; the tool reads each invoice rather than assuming. It has caught mistakes in
  *both* directions (a domestic purchase wrongly reverse-charged, and vice-versa).
- **Reverse charge "AUTO".** In FreeAgent, a reverse-charge line correctly shows a 0% rate — the
  charge is carried by the EC-status flag, not the rate. The tool sets this explicitly so it's
  consistent and visible.
- **UK rail travel is zero-rated**, not reverse charge, even where the booking provider also has a
  non-UK entity in its footer.

## The one-off back-audit

On install (or any time), the owner can run a **historical back-audit**. It reviews existing
explanations and produces a report of:
- money-out entries **missing a receipt**;
- **reverse-charge entries to double-check** (each verified against its actual invoice);
- which VAT periods are **filed** (so anything found there is flagged to you, not changed).

This is a health-check on past bookkeeping — it surfaces items for review; it fixes nothing on its
own.

## What it does *not* do

- It does not file VAT returns or submit anything to HMRC.
- It does not move money, pay bills, or make payments.
- It does not change filed periods.
- It does not give tax advice — judgement calls and edge cases are surfaced for a human (and, where
  relevant, for you).

## Questions

Happy to walk through any specific transactions, show you the audit-marker filter in FreeAgent, or
share the underlying rules (`skill/references/vat-rules.md` in the repo).
