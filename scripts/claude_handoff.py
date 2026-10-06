"""Hand-off between the Modal pipeline and Claude's resume tailoring (2026-10-06).

Why a hand-off: Claude writes the resumes, but it can only move files through the Google Drive
connector, where a ~100 KB PDF costs tens of thousands of tokens per upload. A tailored resume
as markdown is ~9 KB of text. So:

  1. Modal (write_sheet.py) logs qualified jobs to the Sheet and lists the ones still waiting
     for a resume in Drive `Claude Resumes/claude_queue.json` (state: awaiting_resume.json).
  2. Claude (tailor-from-sheet skill, 5:15 / 14:15 / 21:15 ET) reads the queue and writes one
     markdown resume per job into `Claude Resumes/_drafts`.
  3. Modal (render_claude_resumes.py, :55 past those hours and at the start of every run)
     renders each draft to the branded PDF, uploads it to `Claude Resumes`, writes the link into
     the Sheet's "Resume Path" column and Claude's notes into "Resume Notes", then moves the draft
     to `_done` and drops the job from the queue.

Draft format: an HTML comment block, then the resume markdown.

    <!-- claude-resume
    key: linkedin:4012345678
    accent: #005EB8
    status: ready            (or: flagged)
    notes: coverage 92% | not claimed: Snowflake
    -->
    # CHIDVILAS PARUSHA
    ...
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import state

# Drive folder "Job Applications/Claude Resumes" and its parts (owner: parushacv@gmail.com).
RESUMES_FOLDER_ID = "1bE2FxwpPVtP1Aqkt21kJetjMvqX20EsG"
DRAFTS_FOLDER_ID = "1VZQO5OLjyRI-5ut89iZ-CR7BSF5imPD5"
DONE_FOLDER_ID = "1pucha6JEJuQNeAQM76H5vkAPJMRGruq0"
QUEUE_FILE_ID = "1xfEXFq91SX_WJcK8p2w1NzzN2WlYObcq"      # claude_queue.json
BASE_RESUME_FILE_ID = "1fYaEbo02JuCVbjFpYqWTn-8QcGWAQ0cJ"  # base_resume.md (Claude reads it)

AWAITING = "awaiting_resume.json"
QUEUE_DESCRIPTION_CHARS = 8000   # enough to tailor against; keeps the queue file small

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
        upload_file(out, "claude_queue.json", RESUMES_FOLDER_ID, "application/json",
                    existing_id=QUEUE_FILE_ID)
    except RuntimeError:
        # The queue file was deleted by hand: create a new one (Claude finds it by name).
        upload_file(out, "claude_queue.json", RESUMES_FOLDER_ID, "application/json")
    return len(jobs)


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
