---
name: tailor-from-sheet
description: Claude's scheduled resume tailoring for Chidvilas Parusha. Reads the jobs waiting for a resume from Drive claude_queue.json (filled by the Modal pipeline from the Job Application Tracker Sheet), writes a tailored ATS-safe resume from the base resume for each, checks it, and saves it as a draft in Drive for Modal to render into the branded PDF and link in the Sheet. Use when asked to tailor resumes from the Sheet or queue, or when the 5:15 / 14:15 / 21:15 ET scheduled run fires.
---

# Tailor resumes from the queue (Claude path, since 2026-10-06)

How the work is split (details in `scripts/claude_handoff.py`):

| When (ET) | Who | What |
|---|---|---|
| 5:00, 14:00, 21:00 | Modal `run_pipeline` | fetch LinkedIn Data Engineer jobs, score, log every qualified job (>= 50% match) to the Sheet with its full job description and an EMPTY Resume Path, and list the jobs waiting for a resume in Drive `claude_queue.json` |
| 5:15, 14:15, 21:15 | **Claude (this skill)** | read the queue, write one tailored resume per job as a markdown draft in Drive `_drafts` |
| 5:55, 14:55, 21:55 (+ start of each :00 run) | Modal `render_resumes` | render each draft to the branded PDF (<= 2 pages), upload it, write its link into the Sheet's **Resume Path** (col E) and Claude's notes into **Resume Notes** (col R), move the draft to `_done`, drop the job from the queue |

Claude never uploads PDFs (a PDF through the Drive connector costs tens of thousands of tokens)
and never edits the Sheet directly. Claude never applies to jobs: Chidvilas does.

## Fixed Drive locations (folder "Job Applications/Claude Resumes")

| What | Drive id |
|---|---|
| `claude_queue.json` (jobs waiting, oldest first) | `1xfEXFq91SX_WJcK8p2w1NzzN2WlYObcq` |
| `base_resume.md` (source of truth, private, never commit it) | `1fYaEbo02JuCVbjFpYqWTn-8QcGWAQ0cJ` |
| `_drafts` folder (Claude writes here) | `1VZQO5OLjyRI-5ut89iZ-CR7BSF5imPD5` |
| `_done` folder (rendered drafts) | `1pucha6JEJuQNeAQM76H5vkAPJMRGruq0` |

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
4. `pip install --break-system-packages -r requirements.txt` if needed (only `scripts/check_resume.py`
   is run here; no PDF rendering is needed in Claude's session).

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

Style and format
- No em dashes or en dashes anywhere (use commas, colons, periods or a plain hyphen).
- No filler: "leveraging", "spearheading", "passionate", "proven track record",
  "cutting-edge", "synergy", "results-driven". Plain, specific, active verbs.
- Spell out an acronym once where the JD uses the long form, e.g. "Model Context Protocol (MCP)".
- Layout is the repo's single-column template (`templates/resume_classic.html`): ATS-safe,
  standard headings, no tables or images. Font is always Source Sans 3 (bundled). Maximum two
  pages: the renderer tightens spacing automatically; keep the content to roughly the base
  resume's length so it fits.
- Accent color = the company's main brand color as `#RRGGBB` (from what you know or a quick web
  search for "<company> brand color hex"). The renderer darkens it for readability. If unsure,
  leave the `accent:` line out: Modal then uses the company logo's color, else navy.

## Per job

1. Write the resume to `output/tailored/<id> - <Company> - <Title>.md` following the rules above
   (strip `< > : " / \ | ? *` from names).
2. Check it:
   ```bash
   python3 scripts/check_resume.py "output/tailored/<file>.md" \
     --matched "<matched_keywords, comma separated>" --gaps "<gap_keywords, comma separated>"
   ```
   It must print PASS. Fix exactly the listed problems and re-check (at most 2 fixes). Aim for
   keyword coverage >= 90%; when honest coverage is lower because of real gaps, that is fine,
   say so in the notes. Never add a tool he lacks to raise the number.
   Optional local preview: `python3 scripts/render_resume.py <md> /tmp/preview.pdf --accent "#RRGGBB"`
   reports the page count (Chromium: `ls /opt/pw-browsers/chromium-*/chrome-linux*/chrome`).
3. Save the draft with Drive `create_file`: title `<id> - <Company> - <Title>.md`,
   `parentId` = the `_drafts` folder, `contentMimeType: text/markdown`,
   `disableConversionToGoogleType: true`, `textContent` = this header followed by the resume:
   ```
   <!-- claude-resume
   key: linkedin:<id>
   accent: #RRGGBB
   status: ready
   notes: coverage 92% | not claimed: Snowflake, Scala
   -->
   # CHIDVILAS PARUSHA
   ...
   ```
4. If a job should not get a resume (the posting is not really a Data Engineer role, the
   description is unusable, or the check keeps failing), save a draft with only the header,
   `status: flagged` and the reason in `notes:`. Modal writes `FLAGGED ...` into the Sheet row.

## Finish

Report in a few lines: drafts written (company, title, coverage %), jobs flagged and why, jobs
left in the queue for the next run. The PDFs and Sheet links appear after Modal's :55 render.
