# claude-code-freeagent

A [Claude Code](https://claude.com/claude-code) skill that turns bank-transaction bookkeeping in
[FreeAgent](https://www.freeagent.com/) into a **review-and-approve** flow.

It watches FreeAgent for transactions that need attention, finds each one's invoice/receipt
(wherever you keep them), works out the VAT / reverse-charge treatment **by reading the actual
invoice**, and prepares each one for your **one-tap approval in chat**. Nothing is ever written to
your live books until you say so.

> **Not a rigid tool — a method + scaffolding that Claude Code adapts to *your* setup.** Your
> invoices might be in Gmail and your Downloads folder; someone else's are in Dropbox, a shared
> drive, or forwarded to an inbox. The skill supplies the control model, the VAT rules, and the
> approve-first discipline; Claude Code wires the invoice-finding to how *you* actually store
> receipts.

## What it does

- **Finds the work.** Detects transactions that are **unexplained** *or* **awaiting approval**
  (auto-explained by one of your FreeAgent bank rules and sitting in the approval queue).
- **Finds the receipt.** Across five sources: a hosted/Stripe PDF link, your Downloads folder, a
  Gmail PDF attachment, an **email-body receipt rendered to PDF** (e.g. Trainline), or an invoice
  you've *already* attached (a photo of a paper receipt, a bank-app capture).
- **Matches it properly.** By **billing period**, never by amount alone — because same-price
  monthly subscriptions make amount-matching a trap.
- **Gets the VAT right.** Reads the invoice to decide reverse-charge vs domestic — because a
  vendor's `.com` domain tells you *nothing* (plenty of US-looking SaaS are UK-VAT-registered).
- **Asks before writing.** Presents an approval box per transaction — supplier, amount, matched
  invoice with the reasoning, category, VAT treatment, and exactly what it will write. You approve;
  *then* it writes, and tags the description with an audit marker (default `(CC)`) so every
  Claude-touched entry is filterable.

## Two modes

1. **Runs normally** — a weekly scheduled check preps anything new for your approval.
2. **Back-audit on install** — a one-off historical sweep (`audit.py`) that reviews your *existing*
   explanations for VAT-classification slips and missing receipts, and hands you a report. It
   **flags** errors in already-filed VAT periods for your accountant — it never silently changes a
   filed return.

## The control model (the important part)

- **Approve-first.** No write to your books without your explicit in-chat approval — attachments,
  VAT changes, and approvals all wait for you.
- **Audit trail.** Every transaction Claude touches is tagged with a marker you choose.
- **Read-only where it can be.** Gmail access is read-only. Credentials never enter this repo.
- **Flag, don't fix, filed periods.** Corrections to submitted VAT returns are your accountant's
  call — the skill surfaces them, it doesn't touch them.

## Requirements

- **[Claude Code](https://claude.com/claude-code)** (this is a Claude Code skill).
- A **FreeAgent** account + a free FreeAgent **developer app** (for API access).
- *(Optional but recommended)* a **Gmail** account + a Google Cloud **OAuth client** (read-only) —
  needed only to pull invoices that live in email.
- **macOS/Chrome** if you want the email-body-to-PDF rendering (used for receipts like Trainline).
- Python 3 (stdlib only — no pip installs).

## Get started

**Fastest path:** clone this repo and ask your Claude Code to *"set this up for me"* — it drives
the whole thing (creates config, does the OAuth token exchanges, installs the skill, runs the first
check), and you only do the browser bits (creating the two apps + clicking Approve). See
**[AGENTS.md](AGENTS.md)**, which tells the agent exactly how to run the setup. Or do it by hand:

1. **[docs/SETUP.md](docs/SETUP.md)** — the one-time OAuth setup (FreeAgent + Gmail), config, and
   installing the skill.
2. **[docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md)** — the flow, the scripts, the schedule, the audit.
3. **[docs/FOR-YOUR-ACCOUNTANT.md](docs/FOR-YOUR-ACCOUNTANT.md)** — the control model + VAT
   methodology + audit trail, written for an accountant to review.

## Security & privacy

Your OAuth **credentials live in local files outside this repo** (`~/.config/claude-code-freeagent/`)
and are **never committed** — `.gitignore` enforces it. Gmail scope is **read-only**. Everything runs
locally on your machine against your own accounts.

## Disclaimer

This is a productivity tool, not tax advice. **You and your accountant remain responsible for your
books and VAT returns.** The skill is deliberately approve-first so a human signs off every change,
and it flags (never edits) anything in a filed VAT period.

## Licence

MIT — see [LICENSE](LICENSE).
