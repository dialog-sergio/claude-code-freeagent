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

If a credential file is missing, stop and tell the owner — do not invent credentials. Paths are in
the config file (see `config.example.json` and `docs/SETUP.md` **in the repo** — the docs aren't
copied into the installed skill).

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

**⚠️ The guess rules COPY a previous explanation — including your notes and the audit marker.**
`guess_rule_name: "similar_explained_transactions_rule"` clones the last same-supplier explanation
onto the new transaction: description, appended note, blended VAT rate, the lot. Consequences:

- **The audit marker does NOT prove this one was checked.** It gets cloned onto transactions no one
  has ever looked at. Never treat the marker or an existing note as evidence the guess was
  verified — check `marked_for_review` and the attachment instead.
- **A blended rate is cloned onto a basket it doesn't fit.** Real case: a £10.00 café bill written
  at 3.41% ("sandwich zero-rated, VAT on the soft drink only") was cloned onto a £15.30 bill of
  three coffees and a pastry — carrying a note about items that weren't on it, and under-claiming
  £1.35. A bespoke `--manual-vat` rate is a one-off: **assume the next same-supplier transaction
  inherits it wrongly.**
- **Fix the inherited text with `--set-description`**, which replaces rather than appends
  (`--note` would stack a second note on top of the wrong one).

Default to the whole current period. Skip things that legitimately have no invoice: salary,
dividends, HMRC/VAT payments, inter-account transfers, bill payments (the invoice lives on the
bill), and contactless travel. Mention what you're skipping so nothing looks lost.

**Per-account start-date cutoffs.** Some connected accounts are flagged "personal" in FreeAgent and
carry pre-business history that must not be touched. Config's `account_cutoffs` (keyed by the exact
FreeAgent account name) tells `list_targets.py` and `check_unexplained.py` to ignore anything on
that account dated before its cutoff.

**Payments to the owner (salary, home-office rent, reimbursements, personal spend).** These are
not supplier payments. Each one is a **`Money Paid to User`** explanation with `paid_user` set to
the owner's user url (`GET /v2/users`), no attachment, no VAT:

| What the transfer is | Category | Notes |
|---|---|---|
| Monthly salary | Salary and Bonuses | net pay; matches the payroll figure |
| Home-office rent / use-of-home charge paid to the owner | **Expense Account** | accountant's ruling — NOT "Rent" and NOT "Use Of Home", even though both read right by name |
| Out-of-pocket expense reimbursed | Expense Account | the receipt lives on the expense claim |
| Personal spend on the company card | Director Loan Account | repayment comes back as "Payment from director's loan" |
| Dividend to the owner | **Dividend** | every one, even a round sum that looks like a top-up or a loan; ask the owner if it is not clearly a dividend |

**Dividends also go in the owner's tax tracker.** The owner pays personal tax on dividends through
Self Assessment, so each one is logged where they track it. If config names a `dividend_tracker`
(a spreadsheet the owner keeps), then straight after a dividend is approved and written, add one
row: the bank date, a short description, the amount. Type only the input columns; the sheet works
out the tax itself. Read the rows above first: if the payment is already there (same date and
amount), don't add it twice. At the start of every run, also compare the tracker with every
`Dividend` explanation in the owner's current tax year (6 April to 5 April) and report any that
are missing from the tracker, or in the tracker with a different date or amount. Never fix a
mismatch silently: say what differs and fix it once the owner agrees.

**Check the type as well as the category on a for-approval guess.** The similar-transactions rule
clones whatever was last written, so one wrong month becomes every month: a home-office rent that
had once been booked as a plain `Payment` to "Rent" was cloned as-is for three months, and the
accountant had to redo all of them. A category name that sounds right is not a check. Fix a wrong
guess in one call: `attach.py --eid <eid> --paid-user <user url> --category-url <category url>
--approve`. `list_targets.py` shows a `paid_user:` flag on each explanation for exactly this reason.

## Step 2 — For each transaction, find its invoice

**First, check whether it already has one.** If the transaction (or its explanation) already carries
an attachment, it's probably documented — especially an **image/photo** (the owner snapping a paper
receipt via their bank app) or a bank-generated receipt file. Use what's there and skip the hunt;
don't search for a second invoice. Only go looking if there's genuinely no attachment.

Otherwise, try the sources in order — and be exhaustive, because a single failed search is how an
invoice gets missed:

**⚠️ Once you have the receipt email, ALWAYS enumerate its real attachments before using a link.**
Walk every part for `filename`*.pdf + `body.attachmentId` (`lib.gm_find_pdf_attachment`, or print
the part tree). Suppliers routinely attach BOTH an `Invoice-*.pdf` and a `Receipt-*.pdf` while
*also* embedding a hosted link — and the link re-generates a fresh, byte-different file. **Attach
the emailed invoice** (the tax document), not the receipt (proof of payment) and not a re-download.
Observed on a Stripe-billed SaaS invoice: the hosted-link copy and the emailed copy were identical
in size but different in MD5.

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

**Extract the PDF with `pdftotext -layout <file> -`** (poppler; `brew install poppler` /
`apt-get install poppler-utils`). `-layout` preserves the columns so the tax column and its
numbered footnotes stay attached to the line they belong to.

**The receipt EMAIL is not a substitute for the PDF.** Observed on a £10 SaaS charge: the email
showed only "Total £10.00" with no tax line, while the PDF carried a `0%` tax column, the footnote
"Tax to be paid on a reverse-charge basis", and both parties' VAT numbers. The correct call was
only provable from the PDF. If a PDF genuinely cannot be read, say so plainly in the approval box
rather than presenting an email-body inference as if you had read the invoice.

**Inverse trap: a supplier holding a GB VAT number has NOT necessarily charged it.** An EU
supplier can be GB-registered and still zero-rate the supply because the customer's VAT number is
on the bill-to — that is textbook B2B reverse charge. Read the tax column and footnote, never the
letterhead.

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
- **Never let an unreadable file end the hunt.** If a PDF won't open or a link won't fetch, keep
  going down the source list — enumerate the email's own attachments, check Downloads, render the
  email body. Reporting a tooling limitation is not the same as finding the invoice: it once led to
  an approval box built on email text while two real PDFs sat attached to the same email.
- **Read the invoice for VAT** (`pdftotext -layout`). Guessing reverse charge from the vendor name has produced real
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
