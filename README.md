# Job Application AI Agent

An automated job-search assistant for **Chidvilas Parusha (Data Engineer)**. Three times a day it
finds new Data Engineer (and related) postings on LinkedIn, keeps the ones that match his skills,
and produces a tailored, ATS-checked Word resume for each one. Everything is logged to a Google
Sheet with a clickable link to the resume, its ATS score, and notes to read before applying.

It prepares applications; it never submits them. A human always clicks "apply".

## How it works

Three parts hand work to each other through Google Drive:

```
 5:00 / 14:00 / 21:00 ET   Modal: run_pipeline
   fetch new LinkedIn postings (Apify, only those since the last run, <= 100/day)
   -> title filter, clearance filter, dedup (job id, text fingerprint, Sheet)
   -> keyword match vs resume/skills_inventory.md (two lanes, see below)
   -> company research (OpenRouter free model)
   -> log qualified jobs to the Sheet + write them, with job descriptions,
      to Drive "Claude Resumes/_working/claude_queue.json"

 5:15 / 14:15 / 21:15 ET   Claude scheduled task ("Tailor resumes from job queue")
   follows .claude/skills/tailor-from-sheet/SKILL.md for every queued job:
   write the tailored resume -> truth check (check_resume.py) -> build Word
   (build_docx.py) -> ATS score (ats_check.py, target 90+) -> JD match re-run
   -> save a markdown draft to Drive "_working/_drafts"

 5:55 / 14:55 / 21:55 ET   Modal: render_resumes  (also at the start of every run_pipeline)
   draft -> layout (same build code) -> PDF -> ATS score -> upload ONLY the PDF to
   Drive "Claude Resumes/<YYYY-MM-DD>/<Company> - <Title>/Chidvilas Parusha Resume.pdf"
   -> fill the Sheet row: Resume Path (link to the PDF), ATS Score, Resume Notes
```

Why the hand-off: Claude writes much better resumes than the free model the pipeline used before,
but a Claude scheduled task can only move files through the Google Drive connector. So Claude
saves small markdown drafts, and Modal does the binary Word upload and the Sheet update.

### Which jobs qualify

- **Remote only** (since 2026-10-22): every LinkedIn search uses LinkedIn's Remote filter, and any
  posting still marked on-site or hybrid is dropped, so only remote jobs get a resume.
- **Searches:** "Data Engineer" (55% of the daily fetch budget), "Data Platform Engineer",
  "Forward Deployed Engineer" and "AI Engineer" (15% each).
- **Two lanes** (`scripts/filters.py`, `scripts/score_jobs.py`):
  - Data Engineer titles qualify at **>= 50%** keyword match.
  - Other engineer / developer / architect titles need **>= 60%** and at least 2 core data
    technologies in the job description.
- **Excluded:** sales, solutions, support, field, hardware/civil/electrical/network, data center,
  QA, trainer/annotation, manager/director/head of, junior/intern/grad roles; roles that need a
  security clearance; postings with no link, no company, or under 400 characters of description.
- **Match %** counts concrete technologies only: of the technologies a posting names, how many
  are in `resume/skills_inventory.md`. Generic terms (Agile, Git, SQL, ETL...) still go on the
  resume but do not inflate the score.
- **Never twice:** a job is identified by its LinkedIn id, by a fingerprint of company + title +
  description (catches reposts), and by the Sheet itself, so no job gets a second resume.

### Resume rules (enforced by the skill and the checkers)

- Only what is in `resume/base_resume.md` or `resume/skills_inventory.md` may be claimed.
  Employers, titles, dates, education, certifications and numbers are never changed.
- A tool the job asks for that he lacks is never named. The resume is built around his closest
  tools and the capability is described generically; the missing tool is listed in Resume Notes.
  A missing tool never stops a resume from being made.
- Every job in the queue gets a resume. If a draft ever arrives empty or flagged, the render step
  builds the base resume for that row instead of leaving it blank.
- Calibri, single column, at most 2 pages with page 2 well used (85-93% full: the builder
  shrinks the font when page 2 is too full and stretches spacing when it is too empty), name and
  headings in the company's brand color, role dates bold and right-aligned, no em or en dashes,
  no tables or images. Delivered as a PDF only (since 2026-10-19; no Word copy is stored).

Cover letters (since 2026-10-22): every job also gets a one-page cover letter written for it
(~300 words: a hook with a real achievement, two proof stories matched to the job's top needs,
his Cleveland State master's, MBA and fitting certifications, and a short close), checked by
`scripts/check_cover_letter.py` and saved as a PDF next to the resume.

Drive layout (since 2026-10-08):

```
Claude Resumes/
└── 2026-10-08/
    ├── Deloitte - Forward Deployed Engineer/
    │   ├── Chidvilas Parusha Resume.pdf
    │   └── Chidvilas Parusha Cover Letter.pdf
    └── Capital One - Senior Data Engineer/
        ├── Chidvilas Parusha Resume.pdf
        └── Chidvilas Parusha Cover Letter.pdf
```
- Name in normal case; headline = the job title; storytelling bullets that repeat the job's
  must-have keywords across roles; newest role gets the most bullets (max 10).
- ATS target 90+ (hard skills 50, title 10, job-description wording 15, format 25), then the JD
  match is re-run on the finished resume.

## Google Sheet

"Job Application Tracker", columns A to N:

| Column | Meaning |
|---|---|
| Job Title, Company, Job Link | the posting |
| Match % | keyword match against the skills inventory |
| Resume Path | clickable link to the PDF resume in Drive |
| ATS Score | score of the finished resume (target 90+) |
| Status, Timestamp | for your own tracking; time logged (ET) |
| Company Notes | short company research for the summary and interviews |
| Matched Keywords, Keyword Gaps | what matched; what the job wants that you lack |
| Source, Fingerprint | dedup bookkeeping |
| Resume Notes | read before applying: missing tools, travel, years, sponsorship, ATS breakdown |

## Repository layout

```
modal_app.py                  Modal app: run_pipeline + render_resumes schedules, Telegram alerts
scripts/
  scrape_jobs.py              fetch postings (sources/linkedin.py via Apify), daily cap
  filters.py                  title lanes, exclusions, clearance filter, unusable postings
  score_jobs.py               keyword match % (inventory + tech_lexicon.py), gap tracking
  company_research.py         company notes and focus (OpenRouter)
  write_sheet.py              log jobs to the Sheet, publish the Claude queue
  claude_handoff.py           Drive folder ids, queue and draft format
  render_claude_resumes.py    drafts -> PDF -> Drive -> Sheet (Resume Path, ATS, notes)
  build_docx.py               layout + PDF builder (Calibri, brand color, <= 2 pages, page-2 fill, line-fill report)
  ats_check.py                ATS score + JD match re-run on the finished resume
  check_cover_letter.py       cover letter checks (length, structure, truth, no copied bullets)
  build_cover_letter.py       one-page cover letter Word/PDF with the resume's header and color
  check_resume.py             truth check: only base resume / inventory claims, no new numbers
  validate_resume.py          structure + tailoring validators (shared)
  inventory.py                parses skills_inventory.md (exact matching, never fuzzy)
  keyword_gaps.py             mirrors keyword_gaps.md to Drive
  gws_cli.py, state.py, openrouter.py, text_rules.py, tech_lexicon.py   helpers
  tailor_job.py, render_resume.py   older free-model PDF path (kept, not scheduled)
.claude/skills/tailor-from-sheet/SKILL.md   what the Claude scheduled task follows
.claude/skills/tailor-resume/SKILL.md       interactive tailoring in a live Claude Code session
.claude/hooks/resume_hook.py                blocks malformed tailored resumes on write
resume/skills_inventory.md    every tool and practice he has used (matching source of truth)
resume/tool_review.md         tools seen in job gaps, marked used / not used / open
resume/base_resume.md         the real resume (gitignored, also kept in Drive _working)
templates/                    HTML template + font for the older PDF path
CLAUDE.md                     project rules for Claude Code
PRD.md, PRD_v2.md             original requirements (v1) and v2 changes
GWS_SETUP.md                  Google Workspace CLI setup (OAuth, scopes, first login)
```

## Setup

**You need:** Python 3.12, the [`gws` CLI](https://github.com/googleworkspace/cli)
(see [`GWS_SETUP.md`](GWS_SETUP.md)), and accounts on [Apify](https://apify.com) (free tier),
[OpenRouter](https://openrouter.ai) (free models) and [Modal](https://modal.com). For local
Word page counts, LibreOffice and the Carlito font (metric-compatible with Calibri).

```bash
git clone https://github.com/parushayadav/job-application-ai-agent.git
cd job-application-ai-agent
python -m venv .venv && source .venv/bin/activate     # Windows: py -3.12 -m venv .venv
pip install -r requirements.txt
cp .env.example .env     # fill in apify_api_key, open_router_apikey, Telegram (optional)
```

Put the real resume at `resume/base_resume.md` (gitignored). `google_sheet_id` fills itself in on
the first run.

## Deploying and running

On this Windows machine, Python is `py -3.12` and Modal is `py -3.12 -m modal`.

```bash
# one-time secrets
py -3.12 -m modal secret create job-apply-agent-secrets apify_api_key=... open_router_apikey=... \
    google_sheet_id=... google_drive_folder_id=... TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...
py -3.12 -m modal secret create gws-credentials client_id=... client_secret=... refresh_token=... type=...

# deploy after every change to main
git pull
py -3.12 -m modal deploy modal_app.py

# check what is deployed / see logs
py -3.12 -m modal app list
py -3.12 -m modal app logs job-apply-agent

# run now instead of waiting for the schedule
py -3.12 -m modal run --detach modal_app.py                       # full pipeline
py -3.12 -m modal run --detach modal_app.py::render_resumes       # build waiting drafts only
```

Always use `--detach` for manual runs: without it, a dropped laptop connection stops the run.

The Claude side is a Claude scheduled task (5:15 / 14:15 / 21:15 ET) with the Google Drive
connector. It reads the skill from this repo's `main` branch, so a pushed skill change takes
effect on the next run without any deploy.

Run state (seen jobs, the 100/day cap, keyword gaps, the awaiting-resume queue) lives on the Modal
Volume `job-apply-agent-state`.

## Keeping it accurate

- **New skill or tool you have used?** Add it to `resume/skills_inventory.md` (canonical name,
  then aliases). Only you add skills; the agent never does. `resume/tool_review.md` lists tools
  that keep appearing in job gaps for you to mark.
- **Base resume changed?** Update `resume/base_resume.md` and the copy in Drive
  `Claude Resumes/_working/base_resume.md`, which the Claude task reads.

## Failure alerts

Every scheduled Modal run is wrapped in try/except. On failure it sends a Telegram message titled
`JOB-APPLY-AGENT — WHAT BROKE` and re-raises, so nothing fails silently. Set it up by creating a
bot with [@BotFather](https://t.me/BotFather) (`/newbot`, copy the token into
`TELEGRAM_BOT_TOKEN`), messaging the bot once, and reading your chat id from
`https://api.telegram.org/bot<TOKEN>/getUpdates` into `TELEGRAM_CHAT_ID`.

## Cost

Built to run free: Apify stays under 100 results/day (inside the $5/month free credit), OpenRouter
uses free models, Modal stays inside its free monthly credit, and Claude runs on the existing
subscription.

## Hard rules

- No fabrication: only base resume and inventory claims; missing tools go to notes and
  `keyword_gaps.md`, never onto the resume as tool names.
- No em or en dashes in resumes.
- Never a second resume for the same job; never more than 100 fetched jobs per Eastern day.
- No auto-submitting applications.
- `resume/base_resume.md` holds real personal data and stays out of any public remote.

## License

MIT, see [`LICENSE`](LICENSE).
