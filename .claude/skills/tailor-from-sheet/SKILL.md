---
name: tailor-from-sheet
description: Claude's scheduled resume tailoring for Chidvilas Parusha. Reads the jobs waiting for a resume from Drive claude_queue.json (filled by the Modal pipeline from the Job Application Tracker Sheet), writes a tailored ATS-friendly resume from the base resume for each, ATS-checks the Word version (target 90+, max 10 minutes per resume), and saves it as a draft in Drive for Modal to publish as Chidvilas Parusha <Title>.docx with its path, ATS score and notes in the Sheet. Use when asked to tailor resumes from the Sheet or queue, or when the 5:15 / 14:15 / 21:15 ET scheduled run fires.
---

# Tailor resumes from the queue (Claude path, since 2026-10-06)

How the work is split (details in `scripts/claude_handoff.py`):

| When (ET) | Who | What |
|---|---|---|
| 5:00, 14:00, 21:00 | Modal `run_pipeline` | fetch LinkedIn jobs (Data Engineer, Data Platform Engineer, Forward Deployed Engineer, AI Engineer searches), score them, log qualified ones to the Sheet (Data Engineer titles >= 50% match; other engineer titles >= 60% and >= 2 core data technologies), and list them in Drive `claude_queue.json` with their job descriptions |
| 5:15, 14:15, 21:15 | **Claude (this skill)** | write, check and ATS-score one resume per waiting job; save each as a markdown draft in Drive `_drafts` |
| 5:55, 14:55, 21:55 (+ start of each :00 run) | Modal `render_resumes` | build the same Word file (`scripts/build_docx.py`), score it (`scripts/ats_check.py`), upload it as `Claude Resumes/<YYYY-MM-DD> - <Company> - <Title>/Chidvilas Parusha <Title>.docx`, and fill the job's Sheet row: **Resume Path** (clickable path), **ATS Score**, **Resume Notes** |

Claude never uploads Word or PDF files (binary uploads through the Drive connector cost tens of
thousands of tokens) and never edits the Sheet directly. Claude never applies to jobs:
Chidvilas does.

## Fixed Drive locations

`Job Applications/Claude Resumes` holds only the per-job resume folders. Everything Claude
touches is in its `_working` subfolder:

| What | Drive id |
|---|---|
| `_working/claude_queue.json` (jobs waiting, oldest first) | `1xfEXFq91SX_WJcK8p2w1NzzN2WlYObcq` |
| `_working/base_resume.md` (source of truth, private, never commit it) | `1pamiX3yct94m4wyrAWwrn46asK_bafCQ` |
| `_working/_drafts` folder (Claude writes here) | `1VZQO5OLjyRI-5ut89iZ-CR7BSF5imPD5` |
| `_working/_done` folder (published drafts) | `1pucha6JEJuQNeAQM76H5vkAPJMRGruq0` |

If an id stops working, search Drive for the file or folder by title inside "Claude Resumes".

## Setup each run

1. Read `claude_queue.json` with Drive `read_file_content`. Each job has: key, logged_at, title,
   headline, company, link, match_pct, matched_keywords, gap_keywords, company_focus,
   company_notes, company_logo, description. If `jobs` is empty, report "nothing to tailor" and stop.
2. Skip jobs that already have a draft: search Drive for files in the `_drafts` folder
   (`parentId = '1VZQO5OLjyRI-5ut89iZ-CR7BSF5imPD5'`); a draft's name starts with the job's
   numeric id (the part after `linkedin:`). Take at most **15** of the remaining jobs, oldest first.
3. Read `base_resume.md` with `read_file_content` and save it as `resume/base_resume.md` in the
   repo exactly as written (remove only the markdown escaping the connector adds: `\#` -> `#`,
   `\-` -> `-`, and trailing double spaces). Check: it has `## Summary`, `## Skills`,
   `## Experience` and four `### ` role headings.
4. `pip install --break-system-packages -r requirements.txt` if `docx` (python-docx) is missing.
   LibreOffice (`soffice`) is needed for the page count; if it is missing, build without the
   count and say so in the report.

## Resume rules (agreed with Chidvilas, updated 2026-10-07)

Goal: every resume reads as written for THIS job. Two resumes for different jobs should differ
clearly in summary, bullet wording, bullet order and which tools appear where. A reshuffled base
resume is a failure.

What may be claimed
- Everything in the base resume and in `resume/skills_inventory.md` is Chidvilas's real
  experience. Inventory tools (including the "Confirmed by Chidvilas 2026-10-07" section:
  Snowflake, Redshift, Iceberg, Kinesis, EMR, Kubernetes, Scala, CDC, Data Vault, data masking,
  TensorFlow, PyTorch, GraphQL...) may be written as hands-on work in ANY role, used on demand:
  only when this job's description asks for them.
- A job's `gap_keywords` that are NOT in the inventory (check with `scripts/check_resume.py`)
  stay off the resume as tool names. List them in `notes:` so he can prepare.
- Cover every required skill: when the JD names a tool he hasn't used for something he HAS done,
  write the capability generically instead of the tool. He has done orchestration and data
  ingestion in every role ("Orchestration" and "Data Ingestion" are in the inventory). Examples:
  JD wants Dagster or Prefect -> "built pipeline orchestration with dependency management and
  retries" (plus Airflow / MWAA / Databricks Workflows / Step Functions if the JD also accepts
  those); JD wants Fivetran or Airbyte -> "built batch and streaming data ingestion pipelines"
  (plus ADF / Talend / Kinesis where relevant). Name a specific tool only if it is in the
  inventory.
- Timeline sanity: never place a tool in a role that ended before the tool existed (an
  interviewer spots it instantly). Rough first-available years: Delta Lake 2019, Unity Catalog
  2022, Delta Live Tables 2022, Delta Sharing 2021, Microsoft OneLake/Fabric 2023, Snowpark 2021,
  Snowpipe Streaming 2023, Snowflake Cortex AI 2023, Amazon Bedrock 2023, Amazon MWAA 2020,
  Apache Iceberg 2018, LangChain 2022, RAG/LLM tooling 2022+, MCP late 2024, Databricks Asset
  Bundles 2023, dbt 2016, Kubernetes 2015. So: Yana (2017-2019) only pre-2019 tools; Cleveland
  State (2021) nothing from 2022 on; HCL and Nomura can take nearly everything.
- Employers, job titles, role headings (`### ...` lines), dates, locations, education and
  certifications stay exactly as in the base resume. Reuse only the base resume's numbers
  (300%, 64.4%, 100+, 50K+, 5+, petabyte-scale...); "8+ years" stays exactly that.

Content
- Header: `# Chidvilas Parusha` (normal case, never all capitals; build_docx.py also enforces it),
  then the job's `headline` (fall back to a cleaned `title`),
  then the contact line copied exactly.
- `## Summary`: 3 to 4 sentences, about 60 to 95 words, rebuilt for this job: open with the
  headline-style title and "8+ years", then the JD's top 6 to 8 required technologies in the
  JD's own wording, the kind of systems the JD describes, and the domains he has (financial
  services, insurance, hospitality). End with one sentence about the company (see Company
  facts), phrased as an aspiration.
- `## Skills`: first line `- Core Skills for This Role: ` + every JD keyword he has (matched plus
  any gap now in the inventory), in the JD's wording, most important first. Then the base
  categories, most relevant first, JD items first within each line; add inventory tools the JD
  asks for to the right category.
- `## Education`, `## Certifications`: copy unchanged. Section order as in the base resume.
- `## Experience`: storytelling, not keyword lists. Each bullet = action + what was built (with
  the JD's tools named in context) + why it mattered (a base resume number, or the business
  effect the base resume describes). Keep each project's essence (Smart Claims Assistant
  claims automation; Nomura petabyte market data platform; Cleveland State hospitality
  analytics; Yana enterprise analytics) and its project description line.
  - HCL / The Standard (latest): EVERY JD keyword he has must appear in HCL's bullets, woven
    into the real SCA work (streaming claims ingestion, document intelligence, DLT medallion
    pipelines, data quality framework, Salesforce integration, CI/CD...). Rewrite HCL bullets
    toward the JD's responsibilities rather than reordering the base ones.
  - Repeat the JD's must-have technologies across roles to show long, continuous experience:
    each must-have keyword should appear in at least two roles (summary + Skills + HCL +
    Nomura, and earlier roles where the timeline allows). ATS counts repetition.
  - Bullet counts (max 10 per role, newest most): HCL 9 to 10, Nomura 7 to 9, Cleveland State
    4 to 5, Yana 3 to 4. Update each role's `Skills:` line to the JD keywords used in it.
- Full lines: every bullet should end near the end of a line. After building, run
  `build_docx.py --fill-report`; reword any bullet whose last line is under 70% full (tighten it
  to one fewer line or extend it with real detail to fill the line).

Company facts
- `company_notes` and `company_focus` come from a free model WITHOUT web access and can describe
  the wrong company with the same name (live example: "Bitwise", an IT services firm hiring a
  Databricks lead in Richmond, VA, was described as a crypto exchange). Before using them, check
  they agree with the job description. If they conflict or the JD doesn't say what the company
  does, take the company's business from the JD (or a quick web search), or end the summary
  with a neutral line about the role instead, and mention the mismatch in `notes:`.
- Recruiter or staffing postings (the company name is an agency and the JD describes a
  "confidential" client): write the closing sentence about the client's industry from the JD,
  never about the agency.

Style and format
- No em dashes or en dashes anywhere (use commas, colons, periods or a plain hyphen).
- No filler: "leveraging", "spearheading", "passionate", "proven track record",
  "cutting-edge", "synergy", "results-driven". Plain, specific, active verbs.
- Spell out an acronym once where the JD uses the long form, e.g. "Model Context Protocol (MCP)".
- Output is a Word file built by `scripts/build_docx.py`: Calibri, single column, Word's own
  bullets, standard headings, no tables, images, text boxes, headers or footers. It steps the
  font from 11pt down to 9.5pt until the resume fits **2 pages**. Never more than 2 pages: if
  even 9.5pt needs a third page, cut the least relevant bullets in the oldest roles first.
- Accent color (name, section headings and the bold role dates) = the company's main brand
  color as `#RRGGBB` (from
  what you know or a quick web search for "<company> brand color hex"). It is darkened for
  readability. If unsure, leave the `accent:` line out and navy is used.

## Per job (time box: 10 minutes)

Note the start time. Spend at most **10 minutes** on one job; at the limit, save the best
version that passes the truthfulness check and explain the shortfall in the notes.

1. Save the job description to `output/jd/<id>.txt` and write the resume to
   `output/tailored/<id>.md`, following the rules above.
2. Truthfulness check (must print PASS; fix exactly what it lists):
   ```bash
   python3 scripts/check_resume.py output/tailored/<id>.md \
     --matched "<matched_keywords, comma separated>" --gaps "<gap_keywords, comma separated>"
   ```
3. Build the Word file and run the ATS check on it:
   ```bash
   python3 scripts/build_docx.py output/tailored/<id>.md output/docx/<id>.docx --accent "#RRGGBB" --fill-report
   python3 scripts/ats_check.py output/docx/<id>.docx output/jd/<id>.txt --title "<job title>" \
     --company "<company>" --matched "<...>" --gaps "<...>" --pages <pages from build_docx>
   ```
   Target **90+**. Improve only with honest changes, then rebuild and re-check (at most 3 rounds):
   - `missing_you_have`: tools he has that the resume doesn't mention: add them (Skills, and a
     bullet where the base resume supports it);
   - `title_words_missing`: use the job's title words in the headline and summary;
   - `jd_terms_missing`: use the JD's own wording where it truthfully describes his work;
   - `format_issues`: fix them (usually length: trim bullets).
   `missing_you_lack` are tools he does not have: never add them. If they keep the score under
   90, stop improving, save the resume anyway, and list them in the notes.
   Then re-run the JD match on the finished resume (the `JD MATCH` line ats_check prints): any
   keyword listed as "missing but you have it" must be added and the check repeated. Put the
   final `resume vs JD match` % in `notes:`.
4. Save the draft with Drive `create_file`: title `<id> - <Company> - <Title>.md`,
   `parentId` = the `_drafts` folder, `contentMimeType: text/markdown`,
   `disableConversionToGoogleType: true`, `textContent` = this header followed by the resume:
   ```
   <!-- claude-resume
   key: linkedin:<id>
   accent: #RRGGBB
   status: ready
   ats: 93
   notes: <see below>
   -->
   # CHIDVILAS PARUSHA
   ...
   ```
   `notes:` is ONE line (no line breaks) for Chidvilas to read before he submits: what the
   company does and anything notable about the role; what was hard to match; tools the JD wants
   that he lacks (so he can prepare an answer); anything he should check or change by hand
   before submitting (e.g. "confirm the MCP bullet wording", "JD asks for on-site in Austin",
   "requires US citizenship"). Modal adds the ATS score breakdown to it.
5. If a job should not get a resume (not really an engineering role he fits, unusable
   description, or the truthfulness check keeps failing), save a draft with only the header,
   `status: flagged` and the reason in `notes:`. Modal writes `FLAGGED ...` into the Sheet row.

## Finish

Report in a few lines: drafts written (company, title, ATS score), jobs below 90 and why, jobs
flagged and why, jobs left in the queue for the next run. The Word files and Sheet entries
appear after Modal's :55 run.
