# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project State

Built. The full pipeline (scrape, score, tailor, validate, research, log) is implemented in
`scripts/`, gated by `.claude/hooks/resume_hook.py` and `.claude/skills/tailor-resume/SKILL.md`,
and deployable via `modal_app.py`. `PRD.md` is still the source of truth for scope and hard rules —
read it before changing pipeline behavior. This is a Claude Code Masterclass capstone demo project;
treat the PRD's hard rules as binding, not suggestions to redesign.

## What This Builds

An AI-Data-Engineer-job-application agent: scrapes AI Data Engineer postings, scores each against the base
resume, tailors a resume for every job scoring 8+/10, logs qualifying jobs to a Google Sheet, saves
tailored resumes to per-job folders on Desktop, and runs unattended once daily on Modal.

## Commands

No build step, lint config, or test suite exists in this repo — it's a script pipeline, not a
package. `requirements.txt` is deliberately minimal (`requests`, `python-dotenv`); `gws` and
`modal` are separate CLI installs, not pip deps.

Run the pipeline manually, step by step, in order (each writes to `output/`, consumed by the next):

```bash
python3 scripts/scrape_jobs.py        # -> output/raw_jobs.json
python3 scripts/score_jobs.py         # -> output/scored_jobs.json
python3 scripts/tailor_job.py         # automated (OpenRouter) tailoring -> output/tailored_jobs.json, Drive
python3 scripts/company_research.py   # mutates output/tailored_jobs.json in place, adds company_notes
python3 scripts/write_sheet.py        # -> Google Sheet
```

For the interactive tailoring path (Desktop output instead of Drive), use the `tailor-resume` Skill
inside a live Claude Code session instead of `tailor_job.py` — see Architecture below for why these
are two separate code paths.

Test the whole thing end to end through Modal without deploying it: `modal run modal_app.py`.
Deploy the daily cron: `modal deploy modal_app.py` (requires `job-apply-agent-secrets` and
`gws-credentials` Modal secrets — see README.md).

## Architecture

Two independent tailoring paths exist and must not be merged into one:

- **Interactive** (`.claude/skills/tailor-resume/SKILL.md`, run inside a live Claude Code session):
  writes `output/tailored/{folder}.md` via the `Write` tool, which `.claude/hooks/resume_hook.py`
  (wired in `.claude/settings.json` as a `PreToolUse` hook on `Write`, filtered to paths under
  `output/tailored/`) validates before the write is allowed. Delivers to `~/Desktop/{folder}/`.
- **Automated** (`scripts/tailor_job.py`, used by `modal_app.py`): same tailoring prompt and same
  hard rule, but via one OpenRouter call instead of live Claude reasoning (no Anthropic API key
  needed, so it can run headless on Modal's cron). Validates inline by calling `validate()` directly
  since there's no Claude Code session for a hook to attach to. Delivers to Google Drive
  (`google_drive_folder_id`) instead of Desktop, since Modal's container has no Desktop to write to.

Both paths call `scripts/validate_resume.py` for the actual pass/fail rule — it's the single source
of truth so the two paths can't drift apart — and both append to `output/tailored_jobs.json`, though
with different field shapes for the resume location (interactive: `desktop_folder`/`desktop_file`;
automated: `drive_folder_link`/`resume_link`). `scripts/write_sheet.py` reads either shape
uniformly (`job.get("resume_link") or job.get("desktop_file", "")`).

`gws` credentials also differ by environment: locally they're Keychain-encrypted and `gws auth
setup` is interactive (can't be automated); `modal_app.py` has no Keychain, so it materializes a
plain `~/.config/gws/credentials.json` at run time from the `gws-credentials` Modal secret instead.

## Pipeline (build in this order — each step's output feeds the next)

1. **Scrape** — Apify actor `curious_coder/linkedin-jobs-scraper` (free tier) for LinkedIn AI Data
   Engineer postings, remote/hybrid, full-time. Output:
   `{title, company, link, description, posted_date}`.
2. **Score + Filter** — score each job 1-10 against `resume/base_resume.md`, extracting
   `matched_must_haves`/`missing_must_haves` as part of the same call (no separate parse step).
   **Hard cutoff: only 8+ continues.** Log reject count alongside qualified count (e.g. "10
   scraped, 3 qualified") — this is the on-camera proof the filter works.
3. **Tailor Resume** (Skill: `.claude/skills/tailor-resume/SKILL.md`) — reorder/reword the base
   resume to mirror the job's language and keywords. **Never invent experience, employers, tools,
   or metrics.** Reorder and reword only.
4. **Validate** (Hook) — before a tailored resume is saved or logged, check required sections exist
   (Summary, Skills, Experience) and no placeholder text remains. On failure, do not write the row —
   flag it instead.
5. **Company Research** (`scripts/company_research.py`) — per qualifying job, one OpenRouter call
   returns 3-5 talking points about the company/role. This is a plain script, not a Claude Code
   subagent — a real subagent needs a live interactive session, which the Modal headless cron can't
   provide. Used for human context only, never written verbatim into the resume.
6. **Outputs**:
   - Google Sheet row per qualifying job: title, company, job link, fit score, resume path, status,
     timestamp.
   - Desktop folder (interactive path) or Drive folder (Modal path) per qualifying job:
     `{company}-{job-title-slug}/`, containing the tailored resume. The Sheet row references this
     exact folder/file.
7. **Headless + Hosting** — the automated path (`scripts/tailor_job.py`, `scripts/company_research.py`)
   uses OpenRouter instead of live Claude reasoning, so it can run unattended without an Anthropic
   API key. Deployed as a Modal scheduled function (`@app.function(schedule=modal.Cron(...))`),
   once daily. Secrets (Apify key, OpenRouter key, Google creds, Telegram bot token) via Modal
   secrets — never committed.

## Hard Rules

- **8+/10 cutoff is non-negotiable** — nothing below it reaches tailoring, Sheet, or local/Drive
  folders.
- **No fabrication** in tailored resumes — reorder/reword existing content only.
- **No auto-submitting applications** — the agent prepares; a human clicks apply.
- **Resume identity** — `resume/base_resume.md` now holds Chidvilas Parusha's real resume (the
  project originally shipped with a synthetic "Sai Santosh Kumar" stand-in; that's been replaced
  for the user's own personal use). Since it's real personal data (name, email, phone, LinkedIn),
  keep it out of any public remote — see `.gitignore`.
- **Single niche** — AI Data Engineer only, for this demo.
- Wrap the scheduled Modal run in try/except; on any failure, send a Telegram alert named
  `JOB-APPLY-AGENT — WHAT BROKE`, then re-raise. No silent failures.

## Folder Structure (as built)

```
job-apply-agent/
  CLAUDE.md
  PRD.md
  README.md
  GWS_SETUP.md
  .env.example
  .claude/skills/tailor-resume/SKILL.md
  .claude/hooks/resume_hook.py
  resume/base_resume.md
  scripts/
    scrape_jobs.py         # Apify
    score_jobs.py           # scores + extracts matched/missing requirements
    tailor_job.py            # automated tailoring path (OpenRouter, for Modal)
    company_research.py
    write_sheet.py          # Google Sheets
    format_resume_doc.py     # markdown -> real Google Docs formatting
    validate_resume.py       # shared validation logic
  output/                    # gitignored — raw/scored/tailored job data
  modal_app.py                # scheduled entrypoint
  .env                        # gitignored — Apify key, OpenRouter key, Google creds, Telegram bot token
```

## Scoring (built)

`scripts/score_jobs.py` scores each job in `output/raw_jobs.json` 1-10 against
`resume/base_resume.md` via one OpenRouter call per job (`nvidia/nemotron-3.5-lightning:free`), using an explicit
rubric (must-have skills weighted heaviest, then years-of-experience/seniority fit, then
nice-to-haves as a tiebreaker — see the `RUBRIC_PROMPT` constant in the script for exact wording).
The script applies the `score >= 8` cutoff in code, not via a model-declared verdict. Output is
`output/scored_jobs.json` — **both qualified and rejected jobs are kept**, with a `qualified` bool,
so reject counts stay auditable per the PRD's "log the reject count too" requirement. Requires
`open_router_apikey` in `.env`.

## Tailoring + Sheet tracking (built)

`.claude/skills/tailor-resume/SKILL.md` tailors the resume per qualifying job (reorder/reword
only, no fabrication), gated by `.claude/hooks/resume_hook.py` (a `PreToolUse` hook that blocks
the write if required sections are missing or placeholder text remains), then builds a Google Doc
via `gws`, formats it with `scripts/format_resume_doc.py` (converts the markdown structure into
real bold headers/bullets/italics — **never use `gws docs +write`** with raw markdown text, it
inserts `#`/`##`/`-` as literal characters instead of formatting), exports to PDF into
`C:\Users\chidv\OneDrive\Documents\documents\docs new\Chidvilas Resume\Resume\{Company} - {Job
Title}\Chidvilas Parusha {Job Title} Resume.pdf`, and deletes the intermediate Doc. The automated
Modal path (`scripts/tailor_job.py`) mirrors this same folder/filename convention but uploads to a
Google Drive folder instead, since Modal has no access to this local path.
`scripts/write_sheet.py` then logs each `status: "saved"` entry from `output/tailored_jobs.json` to
the "Job Application Tracker" Google Sheet (id cached in `.env` as `google_sheet_id`, and set in the
`job-apply-agent-secrets` Modal secret so scheduled runs append to that same sheet instead of
creating a new one each day), with `Status` starting at `"Not Applied"` for manual tracking.
Dedup keys off the **numeric LinkedIn job id**, not the full URL — LinkedIn stamps per-scrape
tracking params (`position`/`refId`/`trackingId`) into every link, so the same posting returns a
different URL on each run and URL-based dedup would re-add every still-open job daily.

Two `gws` gotchas worth knowing: `files` is a sub-resource of `drive`, not top-level
(`gws drive files export/delete`, not `gws files ...`), and `--output` for `gws drive files export`
is sandboxed to the current directory — `cd` into the target folder and export with a relative
filename, an absolute path is rejected.

## Verification Per Step

- Scrape: returns N jobs with title, company, link, description.
- Score: every job has a numeric score; jobs below 8 are excluded from all downstream steps.
- Tailor: output resume has no placeholder text and passes the validation hook.
- Sheet: row count matches qualifying-job count; every row has a working job link and resume
  reference.
- Local Resume folder: folder count matches qualifying-job count; each folder has exactly one
  resume file.
- Headless run: `claude -p` completes with the same output as the interactive run, restricted to
  the allowed tools.
- Modal: scheduled function deploys, manual trigger runs end to end, forced failure produces the
  named Telegram alert.
