# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project State

Built, v2. The full pipeline (scrape, keyword-match score, research, tailor, validate, render,
log) is implemented in `scripts/`, gated by `.claude/hooks/resume_hook.py` and
`.claude/skills/tailor-resume/SKILL.md`, and deployed via `modal_app.py`. `PRD.md` (v1 base) plus
`PRD_v2.md` (targeting, keyword matching, branded resumes, 3x daily — supersedes the v1 rules it
names) are the source of truth for scope and hard rules — read both before changing pipeline
behavior. Treat their hard rules as binding, not suggestions to redesign.

## Change 2026-10-06: Claude writes the resumes (Word, ATS-checked)

The free-model resumes were not good enough, so the Modal pipeline no longer writes resumes
(`tailor_job.py` is kept but not run). Flow, all in `scripts/claude_handoff.py`:
`run_pipeline` (5:00/14:00/21:00 ET) logs qualified jobs to the Sheet and lists them, with their
job descriptions, in Drive `Claude Resumes/_working/claude_queue.json` -> a Claude scheduled task
(5:15/14:15/21:15 ET) follows `.claude/skills/tailor-from-sheet/SKILL.md`: writes each resume,
checks truthfulness (`check_resume.py`), builds the Word file (`build_docx.py`: Times New Roman,
company color, <= 2 pages via LibreOffice page count) and ATS-scores it (`ats_check.py`, target
90, at most 10 minutes per resume), then saves a markdown draft to `_working/_drafts` ->
`render_resumes` (5:55/14:55/21:55 ET, and at the start of every run) rebuilds the same Word file,
scores it, uploads `Claude Resumes/<YYYY-MM-DD> - <Company> - <Title>/Chidvilas Parusha
<Title>.docx`, and fills the row's Resume Path (clickable path), ATS Score and Resume Notes.

Sheet columns (A-N): Job Title, Company, Job Link, Match %, Resume Path, ATS Score, Status,
Timestamp, Company Notes, Matched Keywords, Keyword Gaps, Source, Fingerprint, Resume Notes.
`write_sheet.migrate_layout()` inserted ATS Score at F once (older rows shift right intact).

Searches: "Data Engineer" (55% of the fetch budget), "Data Platform Engineer", "Forward Deployed
Engineer", "AI Engineer" (15% each). Two lanes (`filters.title_lane`): Data Engineer titles
qualify at >= 50% keyword match; any other engineer/developer/architect title needs >= 60% AND
>= 2 core data technologies in the JD (`score_jobs.CORE_DATA_TERMS`). Excluded titles: sales,
solutions, support, field, mechanical/civil/electrical/hardware/network, data center, QA,
trainer/annotation, manager/director/head of, junior/intern/grads (employer names after " at "
are ignored). Postings without a job link, company or a 400+ character description are dropped.

## What This Builds

A job-application agent for Chidvilas Parusha: fetches new **Data Engineer** postings (all title
variants; Software Engineer was dropped by request), scores each by technology-keyword match against
`resume/skills_inventory.md`, tailors a branded ATS-safe PDF resume for every job with **≥ 50%
match**, logs it to a Google Sheet, records unmatched JD keywords in `keyword_gaps.md`, and runs
unattended 3x daily on Modal.

## Commands

No build step, lint config, or test suite exists in this repo — it's a script pipeline, not a
package. `requirements.txt`: `requests`, `python-dotenv`, `pillow` (logo color), `tzdata`
(Windows has no tz database). `gws` and `modal` are separate CLI installs. On this Windows
machine Python is `py -3.12` (no `python` on PATH) and Modal runs as `py -3.12 -m modal`.
Local PDF rendering uses the installed Chrome/Edge.

Run the pipeline manually, in order (each writes to `output/`, consumed by the next; persistent
state goes to `./state/`, or `$STATE_DIR`):

```bash
python3 scripts/scrape_jobs.py        # -> output/raw_jobs.json (window since last run, 100/day cap)
python3 scripts/score_jobs.py         # -> output/scored_jobs.json, updates keyword gaps + seen jobs
python3 scripts/company_research.py   # adds company_notes/company_focus to scored_jobs.json
# python3 scripts/tailor_job.py       # DISABLED 2026-10-06 (Claude tailors instead)
python3 scripts/write_sheet.py        # -> Google Sheet + Drive claude_queue.json (job descriptions)
python3 scripts/render_claude_resumes.py  # Claude's drafts -> Word files -> Resume Path / ATS Score
python3 scripts/keyword_gaps.py       # mirror keyword_gaps.md to Drive
```

Render one resume by hand: `python3 scripts/render_resume.py <resume.md> <out.pdf> --logo URL`.
Validate one: `python3 scripts/validate_resume.py <resume.md> <job_key>`.

For the interactive tailoring path (local Resume folder instead of Drive), use the `tailor-resume`
Skill inside a live Claude Code session instead of `tailor_job.py`.

Test end to end through Modal without deploying: `py -3.12 -m modal run --detach modal_app.py`.
Deploy the schedule: `py -3.12 -m modal deploy modal_app.py` (requires `job-apply-agent-secrets`
and `gws-credentials` Modal secrets — see README.md). Pull the latest gap report locally:
`py -3.12 -m modal volume get job-apply-agent-state keyword_gaps.md resume/ --force`.

## Architecture

Two independent tailoring paths exist and must not be merged into one:

- **Interactive** (`.claude/skills/tailor-resume/SKILL.md`, live Claude Code session): writes
  `output/tailored/{folder}.md` via the `Write` tool, which `.claude/hooks/resume_hook.py`
  (`PreToolUse` hook on `Write`, filtered to `output/tailored/`) structurally validates; the skill
  then runs the full validator CLI and `render_resume.py` into the local Resume folder.
- **Automated** (`scripts/tailor_job.py`, used by `modal_app.py`): same rules via a free
  OpenRouter model (no Anthropic API key, so it runs headless). The model only writes the Summary
  and picks the bullet ORDER — it is not trusted to rewrite the resume (in testing it invented
  Redshift, "13+ years", a "media" domain, and once garbled the Skills section into nonsense).
  Code assembles everything else: header with JD headline, "Core Skills for This Role" line (every
  matched keyword, JD wording), base skill lines reordered by relevance, base bullets verbatim,
  Education/Certifications verbatim, and a fixed company sentence. Summary is checked
  (length, unknown words, `validate_tailored()`), retried once, else the base summary is used.
  Delivers to Google Drive.

Shared, single-source-of-truth modules (so the paths can't drift):
- `validate_resume.py` — `validate()` (structure; the hook) and `validate_tailored()` (every
  matched keyword present; no gap keyword unless already in base resume/inventory; role headings
  unchanged; no numbers that aren't in the base resume).
- `render_resume.py` + `templates/resume_classic.html` — markdown → HTML → PDF via headless
  Chromium (local Chrome/Edge; Debian `chromium` on Modal), bundled Source Sans 3 font, accent
  color from the company logo (darkened to ≥ 4.5:1 contrast), auto-tightens to ≤ 2 pages. No
  letter-spacing in the template: Chrome emits letter-spaced text as split glyph runs that ATS text
  extraction reads as "SKI L LS".
- `inventory.py` — parses `skills_inventory.md` (`- Canonical | alias, alias`), exact normalized
  lookup (never fuzzy: "Java" must not match "JavaScript").
- `openrouter.py` — all model calls: 4s throttle (free models ~20 req/min), retries transient
  errors, raises `DailyQuotaExceeded` immediately on the per-day cap (retrying can't help).
- `gws_cli.py` — `gws` wrapper (Windows npm-shim workaround), Drive folder/file upload.
- `state.py` — persistent JSON state in `STATE_DIR` (Modal Volume `job-apply-agent-state` at
  `/state`): `run_state.json` (last fetch time, fetched-per-day), `seen_jobs.json`,
  `unscored_jobs.json` / `pending_jobs.json` (carry-over queues), `keyword_gaps.json`.
- `sources/` — pluggable job boards. Each exposes `fetch(window_seconds, limit)` returning
  `base.make_job(...)` dicts keyed `"{source}:{id}"`. Add a board = one module + one line in
  `sources/__init__.py` + `JOB_SOURCES` env var. Nothing downstream changes.

Scoring (`score_jobs.py`): **code first** scans the JD (company name blanked out, so "Oracle"
the employer isn't Oracle the database) for every inventory skill/alias (→ matched) and every
`tech_lexicon.TECH_TERMS` technology not in the inventory (→ gap), so the same posting scores
the same every run — the model's own list varied wildly (one posting: 34% then 100%). The
model's extraction then only adds keywords the lists don't know, and only if they literally
appear in the JD; a model-proposed match must resolve to a real inventory skill sharing a
meaningful word with it. Each skill counts once. `match_pct` counts **concrete technologies
only** — `GENERIC_TERMS` (Agile, Git, CI/CD, SQL, ETL, Data Quality, AI-assistant mentions…)
still go on the resume but are excluded from the %, since they made e.g. a Go/gRPC role score
70%. Qualified if ≥ 50% and ≥ 3 concrete technologies. Qualified and rejected jobs are both kept
in `scored_jobs.json`.

Crash safety: jobs are marked seen at scoring (the fetch window moves on), so qualified jobs go
straight into `pending_jobs.json`; research and tailoring work from that queue, tailoring
checkpoints after every job, and uploaded-but-unlogged rows sit in `unlogged_jobs.json` until
`write_sheet.py` logs them. A run killed at any point loses nothing. Use `modal run --detach`
for manual tests — without it, a dropped local connection stops the app mid-run.

Dedup (all free, all before any model call; every filtered-out job is also remembered so the
overlap window can't re-fetch it). Identity is never the URL — LinkedIn stamps per-scrape
tracking params (`refId`/`trackingId`) into every link, so the same posting has a different URL
each run. Instead: (1) **job key** `source:id` (LinkedIn's numeric id, stable per posting; every
fetched job has one; other boards must supply their own id or a query-less URL) in
`seen_jobs.json`; (2) **fingerprint** = hash of company + title + description — LinkedIn gives a
**repost a new id** (EA and Publicis Sapient each got two resumes before this), but the text is
the same. Company is part of the fingerprint, so the same role at two different companies, or two
different openings at one company, are NOT merged — each gets its own resume; (3) the **Sheet**
(durable even if the Modal Volume is lost): matched by job key, by the `Fingerprint` column
(col L), and — only for rows older than that column — by company + title. A repost whose text was
edited counts as a new job (errs toward applying twice, never toward missing a job). Then
`filters.title_matches` (data discipline + engineer/developer; "Software Engineer" alone fails)
and `filters.requires_clearance` (top secret, TS/SCI, security/secret clearance, polygraph;
negated mentions like "no clearance required" are allowed).

LinkedIn (`sources/linkedin.py`) uses Apify search-URL mode with `f_TPR=r<seconds>` so each run
fetches only postings since the previous run (the actor's `datePosted` enum bottoms out at 24h,
which would re-bill the same jobs 3x/day). Apify bills ~$1/1,000 results; the 100/day cap keeps it
inside the $5/month free credit.

`gws` credentials: locally Keychain-encrypted (login is interactive); `modal_app.py` materializes
`~/.config/gws/credentials.json` from the `gws-credentials` secret and runs an auth preflight.
The OAuth app must be **In production** — Testing-mode refresh tokens expire after 7 days
(`invalid_grant`). Login must use explicit `--scopes` (see GWS_SETUP.md).

## Hard Rules

- **≥ 50% keyword match cutoff** (applied in code) — nothing below it reaches tailoring, Sheet,
  or Drive/local folders. (v2; replaced v1's 8+/10.)
- **No fabrication** — resumes may only claim what's in `base_resume.md` or
  `skills_inventory.md` (Claude's rewording keeps facts, tools and numbers; `check_resume.py`). JD keywords the candidate lacks go to `keyword_gaps.md`, never onto the
  resume. Only the human adds skills to the inventory.
- **No em dashes** (or en dashes) in resumes: they read as AI-generated. Four layers: the base
  resume is written without them, the tailoring prompt and skill forbid them, `text_rules.clean_dashes`
  strips any that remain (before render, on folder/file names, on model output), and
  `validate_resume.validate()` rejects them. Keep new resume text and prompts dash-free.
- **No auto-submitting applications** — the agent prepares; a human clicks apply.
- **Resume identity** — `resume/base_resume.md` is Chidvilas Parusha's real resume (real personal
  data); keep it out of any public remote — see `.gitignore`.
- **Targets** — Data Engineer family only (v2). Software Engineer roles and any role requiring a
  security clearance (the candidate has none) are excluded in `scripts/filters.py` before scoring.
- **Never build a resume twice for the same job** — see Dedup below.
- **≤ 100 fetched jobs per Eastern day**, across all runs.
- Wrap each scheduled Modal run in try/except; on any failure, send a Telegram alert named
  `JOB-APPLY-AGENT — WHAT BROKE`, then re-raise. No silent failures.

## Folder Structure (as built)

```
job-application-ai-agent/
  CLAUDE.md  PRD.md  PRD_v2.md  README.md  GWS_SETUP.md  .env.example
  .claude/skills/tailor-resume/SKILL.md
  .claude/hooks/resume_hook.py
  resume/
    base_resume.md          # gitignored, real resume
    skills_inventory.md     # human-curated skills + aliases (matching source of truth)
  templates/
    resume_classic.html     # branded ATS-safe template
    fonts/                  # Source Sans 3 (OFL)
  scripts/
    scrape_jobs.py  filters.py  score_jobs.py  company_research.py  tailor_job.py  write_sheet.py
    keyword_gaps.py  render_resume.py  validate_resume.py  inventory.py  openrouter.py
    gws_cli.py  state.py  text_rules.py
    sources/  __init__.py (registry)  base.py  linkedin.py
  output/                   # gitignored — per-run job data
  state/                    # gitignored — local persistent state (Modal uses a Volume)
  modal_app.py              # scheduled entrypoint, cron 5:00/14:00/21:00 ET
  .env                      # gitignored — keys, google_sheet_id, google_drive_folder_id
```

## Sheet

"Job Application Tracker" (id in `.env` as `google_sheet_id`, also in the Modal secret).
Columns: Job Title, Company, Job Link, Match %, Resume Path, ATS Score, Status, Timestamp (ET),
Company Notes, Matched Keywords, Keyword Gaps, Source, Fingerprint, Resume Notes. Rows logged before 2026-10-05 hold v1 1-10 scores in
"Match %". Dedup keys off `source:id` (LinkedIn: the numeric job id, never the URL — LinkedIn
stamps per-scrape tracking params into every link).

`gws` gotchas: `files` is a sub-resource of `drive` (`gws drive files ...`), and `--upload` /
`--output` are sandboxed to the current directory — run from the file's folder with a relative
name (`gws_cli.upload_file` does this).

## Verification Per Step

- Scrape: ≤ per-run budget fetched, keys `linkedin:<id>`, title-filter + seen counts logged.
- Score: every scored job has `match_pct`; < 50% excluded downstream; gaps recorded.
- Tailor: passes `validate_tailored`; PDF ≤ 2 pages, accent from logo.
- Sheet: one row per saved job, Match %/keywords/gaps filled, no duplicates across runs.
- Modal: `modal run` end to end; forced failure produces the named Telegram alert.
