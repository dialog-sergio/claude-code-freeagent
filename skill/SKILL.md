---
name: freeagent-explain-transactions
description: >-
  Explain and document a business's bank transactions in FreeAgent: find each unexplained,
  awaiting-approval, or invoice-less transaction, locate its invoice (hosted link, local
  Downloads, Gmail attachment, or an email-body receipt rendered to PDF), match it by billing
  period, work out the VAT/reverse-charge treatment by reading the invoice, and prepare each one
  for the owner to approve in chat before anything is written. Use this whenever the user wants to
  explain / reconcile / do their bank transactions, attach missing invoices, chase receipts, run
  monthly or quarterly bookkeeping, check reverse charge on overseas SaaS, or prep for a VAT
  return — even if they just say "do my transactions", "explain these", "find the invoices" or
  "sort my FreeAgent". Prefer this skill over ad-hoc API calls for any FreeAgent bookkeeping task.
---

# Explain the business's bank transactions (prepare → approve → write)

The job: get every bank transaction explained and documented in FreeAgent with the least effort
from the owner. You do all the finding, matching and VAT reasoning; the owner only ever
**approves**. The golden rule: **nothing is written to their live books until they say "approve"
in chat.** Prepare fully, present clearly, then wait.

Everything runs off local API tokens (no MCP needed), so this same skill also runs on a schedule.
Config (credential paths, Downloads dir, audit marker, account cutoffs) is read from a JSON file
— see the repo's `config.example.json`. Scripts live in `scripts/`; VAT logic in
`references/vat-rules.md`; the historical back-audit in `scripts/audit.py`.

## Setup (once per run)

Access tokens last ~1 hour and auto-refresh, but start clean (from the skill's `scripts/` dir):

```bash
python3 -c "import lib; lib.fa_refresh(); lib.gm_refresh(); print('tokens refreshed')"
```

If a credential file is missing, stop and tell the owner — do not invent credentials. Paths are
in the config file (see `config.example.json` / `docs/SETUP.md`).

## Step 1 — Find what needs work

```bash
python3 list_targets.py --from <YYYY-MM-DD> --to <YYYY-MM-DD> --json /tmp/targets.json
```

This returns three buckets:
- **UNEXPLAINED** — no explanation yet; these need a full explain (category + VAT + invoice).
- **FOR-APPROVAL** — auto-explained by a bank rule/guess (`marked_for_review`) and **waiting for
  the owner's approval**. Crucially these have `unexplained_amount == 0`, so a plain "unexplained"
  check is blind to them — you MUST check this state too (it's how a transaction got missed once).
- **MISSING_INVOICE** — already explained money-out with no attachment; these just need the PDF.

**Handling a FOR-APPROVAL one:** a rule already guessed the category (and maybe VAT). Your job is
to *check the guess*, not redo it — read the guessed category/VAT, attach the receipt if one's
missing (café/taxi card payments are usually a photo receipt or need none), correct the VAT only if
the guess is wrong, and present it for the owner to approve. On their go-ahead, clear the review
flag: `python3 attach.py --eid <eid> --approve` (add `--pdf`/`--reverse-charge` in the same call if
you're also attaching/fixing). Approving is what moves it out of their queue.

Default to the whole current period. Skip things that legitimately have no invoice: salary,
dividends, HMRC/VAT payments, inter-account transfers, bill payments (the invoice lives on the
bill), and contactless travel. Mention what you're skipping so nothing looks lost.

**Per-account start-date cutoffs.** Some connected accounts are flagged "personal" in FreeAgent and
carry pre-business history that must not be touched. Config's `account_cutoffs` (keyed by the exact
FreeAgent account name) tells `list_targets.py` and `check_unexplained.py` to ignore anything on
that account dated before its cutoff.

## Step 2 — For each transaction, find its invoice

**First, check whether it already has one.** If the transaction (or its explanation) already carries
an attachment, it's probably documented — especially an **image/photo** (the owner snapping a paper
receipt via their bank app) or a bank-generated receipt file. Use what's there and skip the hunt;
don't search for a second invoice. Only go looking if there's genuinely no attachment.

Otherwise, try the sources in order — and be exhaustive, because a single failed search is how an
invoice gets missed:

1. **Hosted / Stripe link** — many SaaS receipts embed a public PDF link. Search Gmail:
   ```bash
   python3 find_invoice.py gmail-search 'from:<sender> after:YYYY/MM/DD before:YYYY/MM/DD'
   python3 find_invoice.py gmail-fetch <msgid> /tmp/inv.pdf Invoice
   ```
2. **Downloads** — the owner often already downloaded it. **List everything and match by
   amount/period — do NOT rely on a supplier-name search**, which has silently missed a real
   invoice (the OS index hadn't caught it):
   ```bash
   python3 find_invoice.py downloads
   ```
   Then `Read` the likely candidates to confirm.
3. **Gmail attachment** — `gmail-fetch` above also pulls real PDF attachments (e.g. Google
   Workspace invoices, supplier PDFs) that have no public link.
4. **Email body → render to PDF** — some suppliers put the whole receipt in the email body with NO
   PDF and NO link. The classic is **Trainline**: it sends an "e-tickets" email (PDF = the ticket)
   *and* a "booking confirmation" email (no PDF) whose body holds the **priced receipt** (fare +
   booking fee + total + transaction ID + VAT number). Render that confirmation email to a PDF and
   attach it — it's the real receipt:
   ```bash
   python3 find_invoice.py gmail-search 'from:thetrainline.com "booking confirmation" after:YYYY/MM/DD before:YYYY/MM/DD'
   python3 email_to_pdf.py <msgid> /tmp/receipt.pdf   # Chrome headless; ~25s; schedule-safe
   ```
   Match by date + total. Use the **"booking confirmation"** email (has the price), not the
   "e-tickets" one. This same helper works for any email-body-only receipt.

## Step 3 — Match carefully (period, not value)

**Never match on amount alone.** Subscriptions bill the same amount every month, so value +
supplier can staple the wrong month's invoice to a charge. Confirm the match on:
- **billing period / issue date** on the invoice must line up with the charge date (many SaaS bill
  in arrears — e.g. a Google invoice for "1–28 Feb" is charged ~6 Mar);
- **invoice number** uniqueness (read all candidates when a supplier has several);
- for foreign-currency invoices, sanity-check the FX (e.g. $49 → £38.53 ≈ 1.27) — supplier + date +
  a sane rate, not a coincidental amount.

If you can't confidently match, say so and leave it — a wrong attachment is worse than a missing one.

## Step 4 — Work out the VAT / reverse charge

**Open the invoice and read it.** Follow `references/vat-rules.md`. The essential test: did the
supplier charge **UK VAT**? If yes → standard UK purchase (`UK/Non-EC` + 20%). If it's a non-UK
supplier at 0%/"reverse charge" → reverse charge (`Reverse Charge` + `AUTO`). **A `.com` proves
nothing** — plenty of US-looking SaaS are UK-VAT-registered and charge 20%. Set VAT to `AUTO` on
every reverse-charge write (it resolves to 0%, which is correct).

If you spot a VAT error on an **already-explained, already-filed** transaction, don't fix it —
collect it for the accountant (see vat-rules.md).

## Step 5 — Present for approval (the ping)

When a transaction is ready, ping the owner plainly: **"I have a transaction ready to be
approved."** Then show an approval box per transaction — exactly what will be written:

```
### Ready to approve — <Supplier>
| Transaction | <supplier> — <amount>, <date> (<account>) · #<eid or unexplained> |
| Invoice     | <file> — <supplier>, <invoice amount/period>  ✅ matched by <period/FX reasoning> |
| Category    | <category> (unchanged / suggested) |
| VAT         | Reverse Charge + AUTO  (or: UK/Non-EC 20% — supplier charged UK VAT) |
| Will write  | attach PDF · set VAT · append audit marker |
```

If several are ready, show several boxes (or one compact table) so they can approve in a batch.
Always include the match reasoning — it's how they trust it in one glance.

## Step 6 — Write only after "approve"

On their go-ahead, run the write and read it back to confirm:

```bash
# add invoice / set reverse charge on an already-explained transaction:
python3 attach.py --eid <eid> --pdf /tmp/inv.pdf --reverse-charge

# explain an unexplained transaction (create the explanation):
python3 attach.py --bank-transaction <url> --category-url <url> --gross <-amount> \
    --dated-on <YYYY-MM-DD> --pdf /tmp/inv.pdf --reverse-charge
```

`attach.py` appends the audit marker automatically and prints BEFORE/AFTER. Drop `--reverse-charge`
for UK-VAT / domestic purchases. Report the confirmed result.

## Non-negotiables (why they matter)

- **Approve-first.** These are live books feeding HMRC returns. Surprising the owner with an
  unrequested write breaks the whole trust model — always prepare-then-ping.
- **Read the invoice for VAT.** Guessing reverse charge from the vendor name has produced real
  errors both directions. The PDF is the source of truth.
- **Match by period.** Same-price subscriptions make amount-matching a trap.
- **Enumerate Downloads fully.** Name-search has missed invoices that were sitting right there.
- **Flag, don't fix, filed-period VAT.** Corrections to submitted returns are the accountant's call.
- **Never judge an attachment by its filename — read it.** A bank-generated file (e.g. named
  `<bank>-Receipt-<timestamp>.pdf`) is often the **real supplier invoice** the owner saved via their
  bank's receipt capture, NOT junk. So a transaction that already has an attachment is probably
  already documented — open it before deciding it needs anything. Only replace an attachment
  (`attach.py --replace`, which deletes-then-adds, because FreeAgent won't replace on PUT) after
  reading the existing one and confirming it's genuinely wrong (e.g. a blank page). When in doubt,
  leave it and ask.
- **An IMAGE attachment is a photo of a paper receipt — trust it.** Bank feeds sometimes deliver a
  transaction with an image (JPEG/PNG) already attached: that's the owner photographing a physical
  receipt at the point of sale, and it is **very likely already correct**. Never flag such a
  transaction as needing an invoice, and never replace the photo. These are almost always **in-person
  UK domestic** purchases (shop, restaurant, taxi, materials) — so the VAT is **domestic
  (`UK/Non-EC`), not reverse charge**. If verifying, view the image to read the amount/VAT; otherwise
  leave it be — don't create busywork around it.
