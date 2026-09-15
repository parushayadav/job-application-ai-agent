# PRD — Job Application Agent (Masterclass Session 11 Capstone)

Drop this file into the empty project folder as `PRD.md` before recording. Run `claude`, then `/init`,
then point Claude at this file to start planning.

## 1. What This Is

A job application AI agent, built from scratch for the final Claude Code Masterclass video. It
finds AI Data Engineer postings, tailors a resume to each one, and hosts itself to run every day.

**Candidate:** Chidvilas Parusha, AI Data Engineer.
Base resume lives at `resume/base_resume.md` (Azure/Databricks/Spark/Kafka/AI-ML pipelines, 8+ yrs
experience).

## 2. Goal

End to end, one run should:
1. Pull fresh AI Data Engineer job postings.
2. Score each against the base resume's skills/experience.
3. Keep only jobs scoring 8+/10 fit.
4. Tailor the resume per qualifying job (no fabrication).
5. Log each qualifying job to a Google Sheet (job link + resume link + score).
6. Save each tailored resume as a file in its own per-job folder (Desktop locally, Drive on Modal).
7. Run unattended, every morning, hosted on Modal.

## 3. Pipeline Steps

### 3.1 Scrape
- Source: Apify (free tier), an actor that covers LinkedIn job search.
- Niche: AI Data Engineer, remote or hybrid, full-time.
- Output: list of `{title, company, link, description, posted_date}`.

### 3.2 Score + Filter
- Compare each job's requirements against `resume/base_resume.md` skills/experience, extracting
  matched/missing requirements as part of the same scoring call (no separate parse step).
- Score 1-10 fit.
- **Hard cutoff: only jobs scoring 8 or higher continue past this step.**
- Log the reject count too (e.g. "10 scraped, 3 qualified") — this is the on-camera proof the
  filter is doing real work.

### 3.3 Tailor Resume (Skill)
- `.claude/skills/tailor-resume/SKILL.md`
- Input: base resume + the job's matched/missing requirements.
- Output: reordered/re-emphasized experience, mirrored language, matching keywords.
- **Hard rule: never invent experience, employers, tools, or metrics. Reorder and reword only.**

### 3.4 Validate (Hook)
- Before a tailored resume is saved or logged: check required sections are present
  (Summary, Skills, Experience, no placeholder text left over).
- On a validation failure, do not write the row — flag it instead.

### 3.5 Company Research
- `scripts/company_research.py` — per qualifying job, one OpenRouter call returns 3-5 talking
  points (used for context, not written verbatim into the resume). This runs as a plain script,
  not a Claude Code subagent, since the automated Modal path has no live interactive session for a
  subagent to run in.

### 3.6 Outputs
- **Google Sheet** (one row per qualifying job): job title, company, job link, fit score, resume
  file link/path, status, timestamp.
- **Per-job folder**, named `{Company} - {Job Title}/`, containing the tailored resume file
  (`Chidvilas Parusha {Job Title} Resume.pdf`) — under the local Resume folder
  (`C:\Users\chidv\OneDrive\Documents\documents\docs new\Chidvilas Resume\Resume\`) for the
  interactive path, in Google Drive for the automated Modal path (which has no access to the local
  filesystem). The Sheet row references this folder/file either way.

### 3.7 Headless + Hosting
- The automated path (`scripts/tailor_job.py`, `scripts/company_research.py`) uses OpenRouter
  instead of live Claude reasoning, so it can run unattended without an Anthropic API key.
- Deploy as a Modal scheduled function: `@app.function(schedule=modal.Cron(...))`, once daily.
- Secrets (Apify key, OpenRouter key, Google credentials, Telegram bot token) via Modal secrets —
  never committed.
- Wrap the scheduled run in try/except; on any failure send a Telegram alert named
  `JOB-APPLY-AGENT — WHAT BROKE`, then re-raise. No silent failures.

## 4. Out of Scope

- Auto-submitting applications. The agent prepares; a human still clicks apply.
- Sharing the real resume publicly — `resume/base_resume.md` now holds real personal data (name,
  email, phone, LinkedIn); keep it out of any public remote (see `.gitignore`).
- Multiple niches — AI Data Engineer only, for the demo.
- Resume visual design/formatting polish beyond the text content.

## 5. Folder Structure (as built)

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

## 6. Verification Per Step (for plan-mode / done-contract prompting on camera)

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
