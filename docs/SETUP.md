# Setup

One-time setup. Two OAuth connections (FreeAgent required; Gmail optional but recommended), a
config file, and dropping the skill into Claude Code. Budget ~20 minutes.

> **Tip:** Claude Code can *drive* the fiddly OAuth token exchanges for you. Create the apps below
> to get a Client ID + Secret, then ask Claude "set up the FreeAgent (or Gmail) OAuth for this
> skill" — it will generate the approve link, you click Approve, paste the resulting URL back, and
> Claude exchanges it for the tokens and writes the credential file. The manual steps are here too.

## 0. Where things live

```
~/.config/claude-code-freeagent/
├── config.json        # your settings (copied from config.example.json)
├── freeagent.env      # FreeAgent OAuth credentials + tokens   (chmod 600)
└── gmail.env          # Gmail OAuth credentials + tokens        (chmod 600)
```

```bash
mkdir -p ~/.config/claude-code-freeagent && chmod 700 ~/.config/claude-code-freeagent
cp config.example.json ~/.config/claude-code-freeagent/config.json   # then edit it
```

**Never commit these files.** They live outside the repo and `.gitignore` covers the patterns.

## 1. FreeAgent API app (required)

1. Go to **[dev.freeagent.com](https://dev.freeagent.com)**, sign in, **Create new app**.
2. Set an **OAuth Redirect URI** of `https://localhost` (used only to hand back the approval code).
3. Copy the **Client ID** (OAuth identifier) and **Client Secret**.
4. Create `~/.config/claude-code-freeagent/freeagent.env` (chmod 600):
   ```
   FREEAGENT_BASE_URL=https://api.freeagent.com
   FREEAGENT_CLIENT_ID=<your client id>
   FREEAGENT_CLIENT_SECRET=<your client secret>
   FREEAGENT_ACCESS_TOKEN=
   FREEAGENT_REFRESH_TOKEN=
   ```
   *(Use `https://api.sandbox.freeagent.com` + the sandbox to trial it safely first.)*
5. Authorise: open
   `https://api.freeagent.com/v2/approve_app?client_id=<CLIENT_ID>&response_type=code&redirect_uri=https%3A%2F%2Flocalhost`,
   click **Approve**, copy the `https://localhost/?code=…` URL, and exchange the `code` at
   `POST https://api.freeagent.com/v2/token_endpoint` (grant_type=authorization_code) — or just ask
   Claude to do this step. Put the returned `access_token` + `refresh_token` in the file.

## 2. Gmail API (optional — only to pull invoices from email)

1. **[console.cloud.google.com](https://console.cloud.google.com)** → new project (e.g. "Bookkeeping").
2. **Enable the Gmail API** (search "Gmail API" → Enable).
3. **OAuth consent screen** → **Internal** if you're on Google Workspace (skips verification);
   otherwise **External** and add yourself as a **Test user**.
4. **Credentials → Create OAuth client ID → Application type: Desktop app.** Copy the Client ID +
   Secret.
5. Create `~/.config/claude-code-freeagent/gmail.env` (chmod 600):
   ```
   GMAIL_CLIENT_ID=<your client id>
   GMAIL_CLIENT_SECRET=<your client secret>
   GMAIL_SCOPE=https://www.googleapis.com/auth/gmail.readonly
   GMAIL_ACCESS_TOKEN=
   GMAIL_REFRESH_TOKEN=
   ```
6. Authorise with scope `gmail.readonly`, `access_type=offline`, `redirect_uri=http://localhost`,
   approve, and exchange the code at `https://oauth2.googleapis.com/token` — again, Claude can drive
   this. The scope is **read-only**: the skill can read/download mail, never send or delete.

## 3. Config

Edit `~/.config/claude-code-freeagent/config.json`:
- point `downloads_dir` at wherever your invoice PDFs land;
- pick your `cc_marker` (the audit tag);
- add `account_cutoffs` only if a connected account carried in pre-business history (key by the
  exact FreeAgent account name). Bank accounts themselves are auto-discovered — no IDs to set.

## 4. Install the skill

Copy the `skill/` folder into your Claude Code skills directory:
```bash
cp -R skill ~/.claude/skills/freeagent-explain-transactions
```

## 5. First run

From `~/.claude/skills/freeagent-explain-transactions/scripts`:
```bash
python3 -c "import lib; lib.fa_refresh(); print('FreeAgent OK')"       # confirms tokens work
python3 check_unexplained.py                                          # anything needing attention?
```
Then in Claude Code just say **"do my FreeAgent transactions"** — the skill takes over.

## 6. Back-audit (recommended on install)

```bash
python3 audit.py --from <start> --to <today> --json /tmp/audit.json
```
Then ask Claude to work through the report — it reads each reverse-charge invoice to confirm the
VAT, finds the missing receipts, and presents anything wrong for your approval (or flags it for
your accountant if it's in a filed period).

## 7. Schedule it (optional)

Ask Claude Code to create a weekly scheduled task that runs `check_unexplained.py` and, if it finds
work, prepares each item for your approval **without writing anything**. See
[HOW-IT-WORKS.md](HOW-IT-WORKS.md#the-schedule) for the exact task prompt used.
