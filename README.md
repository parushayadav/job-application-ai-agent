# Job Application AI Agent

**Fastest way to use this:** give this whole repo to any Claude Code agent (or Cursor, Codex,
whatever you use) and say "set this up for me." The pipeline order, every environment variable,
and the exact run/deploy commands are all below — nothing else to figure out.

## What This Is

An AI agent that finds new Data Engineer job postings, scores each one by
how many of its technology keywords you actually have, tailors a branded ATS-safe PDF resume to
every job with at least a 50% match, researches the company, and logs it all to a Google Sheet —
hosted on Modal, running 3x a day.

Built as the capstone project for the final session of the Claude Code Masterclass; extended in
v2 (see [`PRD_v2.md`](PRD_v2.md)).

## Architecture

```
Fetch (pluggable sources; LinkedIn via Apify, only postings since the last run, <= 100/day)
    -> Title filter + seen-job dedup (free, no model calls)
        -> Keyword match vs resume/skills_inventory.md (OpenRouter, >= 50% cutoff)
            -> Company Research (OpenRouter)
                -> Tailor + validate + branded PDF (company logo color)
                    -> Google Drive + Google Sheet (gws CLI)
                        -> keyword_gaps.md (JD keywords you don't have yet)
```

Every job gets a match %: of the technologies the posting names, how many are in your skills
inventory. Below 50% it's logged as rejected and never tailored. Keywords you're missing never go
on the resume — they're counted in `keyword_gaps.md`, and frequently requested ones are flagged so
you can add them to the inventory if you genuinely have them (or learn them).

## Setup

**Prerequisites:**
- Python 3.12+
- The [`gws` CLI](https://github.com/googleworkspace/cli) — see [`GWS_SETUP.md`](GWS_SETUP.md) for
  the full walkthrough (Google Cloud project, OAuth, first login)
- An [Apify](https://apify.com) account (free tier)
- An [OpenRouter](https://openrouter.ai) account (free-tier models used by default)
- A [Modal](https://modal.com) account, only if you want to deploy the daily cron

**Install:**

```bash
git clone https://github.com/sskghub/job-application-ai-agent.git
cd job-application-ai-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**Environment:**

```bash
cp .env.example .env
# fill in apify_api_key, open_router_apikey (see .env.example for where to get each)
```

`google_sheet_id` and `google_drive_folder_id` fill themselves in automatically on first run —
leave them blank.

## Running It

Manually, step by step, in order:

```bash
python3 scripts/scrape_jobs.py
python3 scripts/score_jobs.py
python3 scripts/company_research.py
python3 scripts/tailor_job.py
python3 scripts/write_sheet.py
python3 scripts/keyword_gaps.py
```

PDFs are rendered with headless Chrome/Edge locally (Chromium on Modal).

Or as a single test run through Modal (without deploying it):

```bash
modal run modal_app.py
```

## Deploying (daily automatic run)

```bash
modal secret create job-apply-agent-secrets \
  apify_api_key=... open_router_apikey=... \
  google_drive_folder_id=... \
  TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...

modal secret create gws-credentials \
  client_id=... client_secret=... refresh_token=... type=...

modal deploy modal_app.py
```

Runs at 5:00, 14:00 and 21:00 America/New_York. See [`GWS_SETUP.md`](GWS_SETUP.md) for how to get
the `gws-credentials` values, and the Telegram section below for the bot token.

Run state (seen jobs, the 100/day fetch cap, gap counts, retry queues) lives on the Modal Volume
`job-apply-agent-state`, created automatically. Pull the latest gap report with
`modal volume get job-apply-agent-state keyword_gaps.md resume/ --force` (a copy is also put in
the Drive folder every run).

**Cost/limits at 3 runs/day:** Apify ≤ 100 results/day ≈ $3/month (inside the $5 free credit);
OpenRouter ≤ ~250 of the 1,000 free requests/day (needs a one-time 10-credit top-up); Modal well
inside the $30/month free credit. The 100/day cap is the binding limit — more runs per day give
fresher jobs, not more jobs.

## Telegram Failure Alerts

Every scheduled run is wrapped in try/except. On failure it sends a Telegram message so a broken
cron never fails silently. To turn this on:

1. Message [@BotFather](https://t.me/BotFather) on Telegram, run `/newbot`, copy the token it
   gives you into `TELEGRAM_BOT_TOKEN`.
2. Message your new bot once, then hit
   `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser to find your `chat_id`, put that
   in `TELEGRAM_CHAT_ID`.

Without these two set, the pipeline still runs and still fails loudly in the Modal logs — it just
won't message you.

## Honest Status

- Scrape, score/filter, tailor, company research, and Sheet logging all run correctly end to end.
- The resume-upload step had a real macOS-specific bug (a `/tmp` symlink resolution mismatch
  against the `gws` CLI's sandbox check) — fixed in `scripts/tailor_job.py`.
- Telegram alerting is wired into `modal_app.py` but needs your own bot token (above) to actually
  fire.

## After the Sheet Is Ready — Applying

This repo stops at "qualifying jobs, tailored resumes, one spreadsheet row each." Nothing here
auto-submits an application — a human always makes the final click. Two ways to take it from there:

**Recommended — [Simplify Jobs](https://simplify.jobs/copilot)** (free Chrome extension). Fill out
its one-time profile, then it autofills the rest of any job application form for you. Open each
row's job link, drop in your tailored resume, click through. Roughly 30 applications in 30 minutes.

**Alternative — [browser-use](https://github.com/browser-use/browser-use).** An open-source
framework for building your own browser-controlling AI agent. You could wire it up to fully
auto-apply from the Sheet, but it's less reliable than filling forms yourself with autofill.

If you want to build real auto-apply on top of this repo, the tools to look at are
[Playwright](https://github.com/microsoft/playwright) (browser automation) and
[Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp) (lets a coding agent
drive a real Chrome browser). Neither is implemented here — this is just where you'd start.

## Claude Code Building Blocks Used

- **`CLAUDE.md`** — always-on project memory: hard rules, pipeline order, folder layout.
- **A Skill** (`.claude/skills/tailor-resume/`) — the interactive resume-tailoring procedure.
- **A Hook** (`.claude/hooks/resume_hook.py`) — blocks any tailored resume from being saved if it's
  missing a required section or still has placeholder text in it.
- **Company research runs as a plain script**, not a Claude Code subagent — a real subagent needs a
  live interactive session, which Modal's headless daily cron can't provide.

## Limits

- Data Engineer roles only, US, from LinkedIn (more boards plug into `scripts/sources/`).
  Software Engineer roles and roles requiring a security clearance are filtered out, and a job
  (or a repost of it) never gets a second resume.
- The 50% keyword-match cutoff is enforced in code; nothing below it reaches tailoring or the Sheet.
- Tailoring only reorders and rewords what's on the base resume plus skills you listed in
  `skills_inventory.md` — it never invents experience, employers, tools, or metrics, and a
  validator rejects any resume that does.
- A human always clicks the final "apply" — nothing here submits an application on its own.

## License

MIT — see [`LICENSE`](LICENSE).
