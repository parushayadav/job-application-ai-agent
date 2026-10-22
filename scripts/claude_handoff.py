"""Hand-off between the Modal pipeline and Claude's resume tailoring (2026-10-06).

Why a hand-off: Claude writes the resumes, but it can only move files through the Google Drive
connector, where a binary file (Word/PDF) costs tens of thousands of tokens per upload. A
tailored resume as markdown is ~9 KB of text. So:

  1. Modal (write_sheet.py) logs qualified jobs to the Sheet and lists the ones still waiting
     for a resume in Drive `Claude Resumes/_working/claude_queue.json` (state:
     awaiting_resume.json).
  2. Claude (tailor-from-sheet skill, 5:15 / 14:15 / 21:15 ET) reads the queue, writes and
     ATS-checks one resume per job, and saves it as markdown in `_working/_drafts`.
  3. Modal (render_claude_resumes.py, :55 past those hours and at the start of every run)
     builds the layout with the same code Claude checked it with (build_docx.py), scores it
     (ats_check.py), converts it to PDF and uploads only the PDF to `Claude Resumes/<YYYY-MM-DD>/
     <Company> - <Title>/Chidvilas Parusha Resume.pdf` (PDF only since 2026-10-19), fills the row's Resume Path / ATS Score / Resume Notes, moves the
     draft to `_done` and drops the job from the queue.

`Claude Resumes` itself holds only the per-job resume folders; everything else is in `_working`.

Draft format: an HTML comment block, then the resume markdown.

    <!-- claude-resume
    key: linkedin:4012345678
    accent: #005EB8
    status: ready            (flagged is retired: Modal then builds the base resume)
    ats: 93
    notes: Fintech payments company; JD stresses Snowflake (you lack it), mention Databricks SQL
    -->
    # Chidvilas Parusha

Since 2026-10-22 the draft also carries the job's cover letter: after the resume, a line
`<!-- cover-letter -->` and then the letter from "Dear ...," to the signature (see
split_cover_letter; render_claude_resumes.py builds it as "Chidvilas Parusha Cover Letter.pdf").

A draft for a job that is no longer in the queue may add title:, headline:, company:, link:,
jd: (the description on one line), matched: and gaps: (comma separated) to its header.
    ...
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import state

# Drive folder "Job Applications/Claude Resumes" (resumes) and its "_working" subfolder (all
# other files below), owner parushacv@gmail.com. Ids survive moves between folders.
RESUMES_FOLDER_ID = "1bE2FxwpPVtP1Aqkt21kJetjMvqX20EsG"
WORKING_FOLDER_ID = "1wWB3y5Fm-ppbSE9dFoKgEbyRGfQZdD3h"
DRAFTS_FOLDER_ID = "1VZQO5OLjyRI-5ut89iZ-CR7BSF5imPD5"
DONE_FOLDER_ID = "1pucha6JEJuQNeAQM76H5vkAPJMRGruq0"
QUEUE_FILE_ID = "1xfEXFq91SX_WJcK8p2w1NzzN2WlYObcq"      # claude_queue.json
BASE_RESUME_FILE_ID = "1DQbnXPmvn7clDaHOsvqOqQdXCNPhnI8d"  # base_resume.md (Claude reads it)

AWAITING = "awaiting_resume.json"
QUEUE_DESCRIPTION_CHARS = 8000   # enough to tailor against; keeps the queue file small

COVER_MARKER = "<!-- cover-letter -->"   # draft: resume markdown, this line, then the letter
FRONT_MATTER = re.compile(r"^\s*<!--\s*claude-resume\s*\n(.*?)-->\s*\n", re.DOTALL)


def awaiting():
    return state.load(AWAITING, {})


def add_awaiting(jobs, logged_at):
    """Jobs just logged to the Sheet without a resume."""
    queue = awaiting()
    for job in jobs:
        queue.setdefault(job["key"], {
            "key": job["key"],
            "logged_at": logged_at,
            "title": job["title"],
            "headline": job.get("title_family") or job["title"],
            "company": job["company"],
            "link": job.get("canonical_link") or job.get("link", ""),
            "match_pct": job.get("match_pct"),
            "matched_keywords": [m["keyword"] for m in job.get("matched_keywords", [])],
            "gap_keywords": list(job.get("gap_keywords", [])),
            "company_focus": job.get("company_focus", ""),
            "company_notes": job.get("company_notes", ""),
            "company_logo": job.get("company_logo") or "",
            "description": (job.get("description") or "")[:QUEUE_DESCRIPTION_CHARS],
        })
    state.save(AWAITING, queue)
    return queue


def remove_awaiting(key):
    queue = awaiting()
    if queue.pop(key, None) is not None:
        state.save(AWAITING, queue)


def publish_queue():
    """Overwrite Drive claude_queue.json with every job still waiting for a resume, oldest first."""
    from gws_cli import upload_file

    jobs = sorted(awaiting().values(), key=lambda j: j.get("logged_at") or "")
    out = state.STATE_DIR / "claude_queue.json"
    out.write_text(json.dumps({"updated": state.now_utc().isoformat(), "jobs": jobs}, indent=1),
                   encoding="utf-8")
    try:
        upload_file(out, "claude_queue.json", WORKING_FOLDER_ID, "application/json",
                    existing_id=QUEUE_FILE_ID)
    except RuntimeError:
        # The queue file was deleted by hand: create a new one (Claude finds it by name).
        upload_file(out, "claude_queue.json", WORKING_FOLDER_ID, "application/json")
    return len(jobs)


def split_cover_letter(resume_and_letter):
    """-> (resume markdown, cover letter text or ""). Drafts written before 2026-10-22 have no
    cover letter."""
    resume, sep, letter = resume_and_letter.partition(COVER_MARKER)
    return resume.strip() + "\n", letter.strip() if sep else ""


def parse_draft(text):
    """-> (meta dict, resume markdown). Raises ValueError if the header block is missing."""
    match = FRONT_MATTER.match(text)
    if not match:
        raise ValueError("draft has no <!-- claude-resume ... --> header")
    meta = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip().lower()] = value.strip()
    return meta, text[match.end():].strip() + "\n"
