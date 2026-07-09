# AGENTS.md — for a Claude Code (or similar) agent working in this repo

This repo is a **Claude Code skill** that turns FreeAgent bank-transaction bookkeeping into a
**prepare → approve → write** flow. If a user has pointed you here, they want one of two things:
**set it up**, or **use it**. Drive each interactively — don't just hand them the docs.

You can do almost everything. The only steps you *cannot* do are the ones inside the user's own
browser sessions: creating two developer apps and clicking **Approve** on consent screens (you
can't log into their accounts). Everything else — token exchanges, config, install, first run,
schedule, and adapting to how they store receipts — is yours to drive, one step at a time.

## If the user wants to SET IT UP

Walk them through it, pausing for their input. Full detail is in `docs/SETUP.md`.

1. **Prereqs.** Confirm a FreeAgent account. Gmail is optional (only needed to pull invoices from
   email). The email-body-to-PDF helper needs Chrome (currently macOS-oriented).
2. **Config dir.** `mkdir -p ~/.config/claude-code-freeagent && chmod 700 ~/.config/claude-code-freeagent`;
   copy `config.example.json` → `~/.config/claude-code-freeagent/config.json`.
3. **FreeAgent app.** Have them create an app at **dev.freeagent.com** with redirect URI
   `https://localhost`, and paste you the **Client ID + Secret**. Write `freeagent.env` (chmod 600).
   Then **drive the OAuth yourself**: build the `/v2/approve_app` URL → they click Approve → they
   paste back the `https://localhost/?code=…` URL → you exchange it at `/v2/token_endpoint` and
   write the access + refresh tokens. (Exact URLs in `docs/SETUP.md` §1.)
4. **Gmail app (optional).** Same pattern: Google Cloud project → enable Gmail API → OAuth consent
   (Internal if Workspace, else add them as a Test user) → **Desktop** OAuth client → **read-only**
   scope → drive the token exchange. The Google console UI changes often — ask what they see and
   adapt rather than reciting fixed clicks.
5. **config.json.** Set `downloads_dir`, choose the `cc_marker` (audit tag), and add
   `account_cutoffs` only if a connected account carried in pre-business history. Bank accounts are
   auto-discovered — no IDs to configure.
6. **Install the skill.** `cp -R skill ~/.claude/skills/freeagent-explain-transactions`.
7. **First run.** From the scripts dir: `python3 -c "import lib; lib.fa_refresh(); print('OK')"`,
   then `python3 check_unexplained.py`. Report what's found.
8. **Offer** the one-off **back-audit** (`python3 audit.py --from <start> --to <today>`) and a
   **weekly schedule** (task prompt in `docs/HOW-IT-WORKS.md` → "The schedule").

## If the user wants to USE it

The installed skill (`skill/SKILL.md`) carries the full operating procedure. In short: find the
work (unexplained **and** awaiting-approval), find each receipt (hosted link → Downloads → Gmail
attachment → email-body render → an already-attached photo), match by **billing period**, **read
the invoice** to decide the VAT, present an approval box, and **write only after "approve"**.

## Non-negotiables (never break these)

- **Approve-first.** Live books feeding HMRC. Never write — attach, set VAT, approve — without the
  user's explicit in-chat approval.
- **Read the invoice for VAT.** A vendor's `.com` does not decide reverse-charge vs domestic.
- **Never commit credentials.** They live in `~/.config/claude-code-freeagent/` and are gitignored.
- **Flag, don't fix, filed VAT periods.** Surface those for the accountant; don't edit them.
- **Adapt to the user's setup.** Their receipts may live somewhere the current scripts don't cover
  — extend the invoice-finding rather than giving up. That flexibility is the point.

## Map

| File | What |
|---|---|
| `docs/SETUP.md` | Full setup detail (both OAuth flows, config, install, schedule) |
| `docs/HOW-IT-WORKS.md` | Architecture, scripts, transaction states, the schedule |
| `docs/FOR-YOUR-ACCOUNTANT.md` | Control model + VAT methodology (for the user's accountant) |
| `skill/SKILL.md` | The operating procedure |
| `skill/references/vat-rules.md` | VAT / reverse-charge decision rules |
