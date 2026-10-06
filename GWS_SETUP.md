# Setting Up `gws` (Google Workspace CLI)

This project talks to Google Drive, Docs, and Sheets entirely through
[`gws`](https://github.com/googleworkspace/cli), a third-party open-source CLI (not an official
Google product). This guide gets it authenticated, locally and on Modal.

This project only needs three scopes: **Drive, Docs, Sheets.** You do not need Gmail, Calendar, or
any other Workspace API for this pipeline.

## 1. Install `gws`

Pick one:

```bash
# Recommended: pre-built binary
# Download from https://github.com/googleworkspace/cli/releases and put `gws` on your $PATH

# Or via npm (Node.js 18+)
npm install -g @googleworkspace/cli

# Or via Homebrew (macOS/Linux)
brew install googleworkspace-cli
```

Confirm it's installed:

```bash
gws --version
```

## 2. Authenticate (pick A or B)

### Option A — you have `gcloud` installed (fastest)

```bash
gws auth setup     # walks you through creating a Cloud project + enabling APIs
gws auth login --scopes "https://www.googleapis.com/auth/drive,https://www.googleapis.com/auth/documents,https://www.googleapis.com/auth/spreadsheets"
```

> **Scope warning:** an unverified ("testing mode") OAuth app can only consent to ~25 scopes.
> `gws auth login` with no `-s` flag defaults to a much larger "recommended" preset and will fail.
> Always pass the three explicit `--scopes` above. `-s drive,docs,sheets` only narrows a picker and can
> leave the token with no Drive/Docs/Sheets scopes (`403 insufficient authentication scopes`); check
> with `gws auth status`.

### Option B — no `gcloud`, manual Google Cloud Console setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create a project (or pick
   an existing one).
2. Open **APIs & Services → OAuth consent screen** for that project:
   - App type: **External**
   - **For the Modal cron, set Publishing status to "In production"** (Audience → Publish app).
     In Testing mode Google expires refresh tokens after **7 days**, and the scheduled run then
     fails with `invalid_grant`. You do not need to submit for verification for personal use —
     you'll just see a "Google hasn't verified this app" warning at login.
3. Under **Test users**, click **Add users** and add your own Google account email. Skipping this
   step is the #1 cause of a generic "Access blocked" error on login.
4. Open **APIs & Services → Credentials → Create Credentials → OAuth client ID**:
   - Application type: **Desktop app**
5. Download the client JSON and save it to:
   ```
   ~/.config/gws/client_secret.json
   ```
6. Log in:
   ```bash
   gws auth login --scopes "https://www.googleapis.com/auth/drive,https://www.googleapis.com/auth/documents,https://www.googleapis.com/auth/spreadsheets"
   ```

Either path opens a browser for the OAuth consent screen. Approve it, and `gws` stores encrypted
credentials locally (AES-256-GCM, key in your OS keychain).

## 3. Verify it works

```bash
gws drive files list --params '{"pageSize": 5}'
```

If that returns JSON with a `files` array (even an empty one), you're authenticated correctly.

## 4. Getting credentials onto Modal (headless)

Modal's containers have no browser and no OS keychain, so the interactive flow above won't work
there. Export your already-authenticated local credentials instead:

```bash
gws auth export --unmasked > /tmp/gws_credentials.json
cat /tmp/gws_credentials.json
```

This prints a JSON object with `client_id`, `client_secret`, `refresh_token`, and `type`. Create a
Modal secret named `gws-credentials` with those four values (Modal dashboard → Secrets → Create
new secret, or `modal secret create gws-credentials client_id=... client_secret=... refresh_token=... type=...`).
`modal_app.py` reads this secret at runtime and reconstructs `~/.config/gws/credentials.json`
inside the container automatically — you don't need to touch that part of the code.

Delete `/tmp/gws_credentials.json` locally once the secret is created — it's a real, live
credential and should never be committed or left sitting on disk.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Access blocked: ... has not completed the Google verification process" | Add yourself as a test user (Option B, step 3) |
| Scope picker fails / consent screen errors on a wide scope preset | Use `-s drive,docs,sheets` explicitly, not the default preset |
| "Google hasn't verified this app" warning during login | Expected in testing mode — click **Continue** |
| Modal run fails with `invalid_grant` | Refresh token expired (Testing mode = 7-day tokens) or revoked. Publish the app to "In production", re-run the `--scopes` login above, re-export, and update the `gws-credentials` secret |
| Works locally but fails on Modal | Confirm the `gws-credentials` Modal secret has all four fields (`client_id`, `client_secret`, `refresh_token`, `type`) |

Full reference: [github.com/googleworkspace/cli](https://github.com/googleworkspace/cli)
