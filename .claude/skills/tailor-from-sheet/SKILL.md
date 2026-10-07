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
| `_working/base_resume.md` (source of truth, private, never commit it) | `1fYaEbo02JuCVbjFpYqWTn-8QcGWAQ0cJ` |
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

## Resume rules (agreed with Chidvilas, 2026-10-06)

Truthfulness
- Only claim what is in the base resume or `resume/skills_inventory.md`. A job's
  `gap_keywords` that are not in the inventory are tools he does NOT have: never put them on the
  resume. `scripts/check_resume.py` knows which gaps have since been added to the inventory.
- Employers, job titles, role headings (`### ...` lines), dates, locations, education and
  certifications stay exactly as in the base resume.
- No new numbers or metrics. Reuse the base resume's numbers only (300%, 64.4%, 100+, 50K+...).
  "8+ years" stays exactly that.
- MCP (Model Context Protocol), RAG, dbt, LangChain, Pydantic and Apache Kafka were used at
  HCL / The Standard (Smart Claims Assistant). When the JD asks for them they may appear in
  that role's bullets and Skills line, the summary and the Skills section. Describe them as
  part of the work that role already lists (claims documents, data quality, streaming,
  ingestion); do not invent outcomes or metrics for them, and never put them under other roles.

Content
- Header: `# CHIDVILAS PARUSHA`, then the job's `headline` (fall back to a cleaned `title`),
  then the contact line copied exactly.
- `## Summary`: 3 to 4 sentences, about 60 to 95 words. Open with the headline-style title and
  "8+ years", weave in the JD's most important matched keywords in the JD's own wording, mention
  only domains the base resume has (financial services, insurance, hospitality). End with one
  sentence about the company using `company_focus` (or `company_notes`), phrased as an aspiration, e.g.
  "Looking to bring this experience to Acme's work in payments infrastructure."
- `## Skills`: first line `- Core Skills for This Role: ` + every `matched_keywords` entry plus
  any `gap_keywords` entry now in the inventory, in the JD's wording. Then the base categories,
  most relevant category first and JD-matched items first within each line. Add inventory
  tools the JD asks for to the right category.
- `## Education`, `## Certifications`: copy unchanged. Section order as in the base resume.
- `## Experience`: keep every role. Reorder bullets so the most relevant come first, and reword
  them toward the JD's language and keywords while keeping what was actually done, the tools
  and the numbers. Keep each role's project description line and `Skills:` line (update the
  Skills line order to put JD keywords first). Trim the least relevant bullets if needed to fit
  two pages: about 8 to 10 for HCL and Nomura, 4 to 6 for Cleveland State, 3 to 5 for Yana.

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
- Output is a Word file built by `scripts/build_docx.py`: Times New Roman, single column, Word's
  own bullets, standard headings, no tables, images, text boxes, headers or footers. It steps
  the font from 11pt down to 9.5pt until the resume fits **2 pages**; if even 9.5pt needs a third
  page, trim the least relevant bullets.
- Accent color (name and section headings) = the company's main brand color as `#RRGGBB` (from
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
   python3 scripts/build_docx.py output/tailored/<id>.md output/docx/<id>.docx --accent "#RRGGBB"
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
