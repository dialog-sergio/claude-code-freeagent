# How it works

## Architecture

The skill is **self-contained**: every script talks to FreeAgent and Gmail using **local OAuth
tokens and the Python standard library only** — no MCP connectors, no pip installs. That's the
design choice that lets the *same* code run two ways:

- **Interactively** — you say "do my transactions" and Claude Code drives the scripts + reasoning.
- **Headless / scheduled** — a cron-style task runs the watcher unattended (MCPs usually aren't
  available in scheduled runs; local-token API calls are).

Bank accounts are **discovered from the API** (`/v2/bank_accounts`), so there are no account IDs to
configure. Everything personal (credential paths, Downloads dir, audit marker, per-account cutoffs)
lives in `~/.config/claude-code-freeagent/config.json`.

## The scripts

| Script | Role |
|---|---|
| `lib.py` | Shared helpers: token refresh, FreeAgent + Gmail API, Downloads enumeration, config. |
| `check_unexplained.py` | The **watcher**. Cheap, read-only. Reports transactions **unexplained** *or* **awaiting approval**. Exits non-zero if there's work — a scheduler branches on it. |
| `list_targets.py` | Fuller picture over a date range: unexplained, for-approval, and explained-but-no-receipt. |
| `find_invoice.py` | Locate an invoice: `downloads` (enumerate all PDFs), `gmail-search`, `gmail-fetch` (PDF attachment **or** hosted Stripe link). |
| `email_to_pdf.py` | Render an **email-body** receipt (e.g. Trainline) to a PDF via headless Chrome. |
| `audit.py` | The **back-audit** — historical health-check report (missing receipts, reverse-charge to verify, filed periods). |
| `attach.py` | The **only writer**. Attaches a PDF, sets VAT, appends the audit marker, and (with `--approve`) clears the review flag. Run only after the owner approves. |

## The flow (per transaction)

The detailed procedure is in [`skill/SKILL.md`](../skill/SKILL.md). In short:

1. **Find the work** — unexplained or awaiting-approval.
2. **Find the receipt** — five sources, in order:
   hosted/Stripe link → Downloads (enumerate all, match by period) → Gmail PDF attachment →
   email-body rendered to PDF → *already attached* (a photo receipt / bank capture — trust it).
3. **Match by period**, never by amount alone.
4. **Read the invoice** to decide the VAT treatment.
5. **Present an approval box** — nothing is written yet.
6. **Write only after "approve"**, then read it back to confirm.

## Two transaction states (both matter)

- **Unexplained** — no explanation. Obvious.
- **For approval** (`marked_for_review`) — one of your FreeAgent **bank rules** already guessed an
  explanation, and it's sitting in the approval queue. These have `unexplained_amount == 0`, so a
  naïve "unexplained only" check is **blind** to them. The watcher checks both. (This was a real
  miss that prompted the fix — bank rules doing first-pass categorisation is great, but the tool
  has to notice the queue.)

## The schedule

A weekly task runs `check_unexplained.py`; if it finds work, it invokes the skill to **prepare**
each item and present approval boxes — **writing nothing**. The task prompt, in essence:

> Run `check_unexplained.py`. If CLEAR, stop. If WORK, invoke the skill: for unexplained items find
> + period-match the invoice and work out the VAT; for for-approval items check the rule's guess
> rather than redo it. Present one approval box per transaction and say "I have N ready to approve."
> **Write nothing** — no attachments, VAT changes, or approvals — until the owner approves in chat.

Because the skill is local-token based, this runs on your machine with access to your Downloads and
credentials.

## Design lessons baked in

Each of these is here because ignoring it caused a real error:

- **Read the invoice for VAT.** Vendor domain ≠ VAT treatment. Wrong in both directions otherwise.
- **Match by billing period.** Flat-rate monthly subscriptions defeat amount-matching.
- **Enumerate Downloads fully.** A name-search silently missed an invoice that was right there.
- **Never judge an attachment by its filename — read it.** A bank-named receipt file is often the
  real invoice; an image attachment is usually a photo of a paper receipt (domestic, not reverse
  charge). Don't replace what's already correct.
- **Flag, don't fix, filed periods.** Submitted returns are the accountant's domain.
- **Approve-first, always.** Live books feeding HMRC — a human signs off every write.
