"""Log every qualified job to the "Job Application Tracker" Google Sheet, with its full job
description, so Claude can tailor the resume afterwards (2026-10-06 change).

The pipeline no longer builds resumes (the free-model resumes were not good enough). This step
reads the qualified-job queue (STATE_DIR/pending_jobs.json, filled by score_jobs.py and enriched
by company_research.py) and appends one row per job that isn't already logged (deduped by
`source:id` job key). "Resume Path" is left EMPTY: Claude's scheduled tailoring run fills it in
(see .claude/skills/tailor-from-sheet/SKILL.md), together with "Resume Notes".

Legacy input still honoured: output/tailored_jobs.json and unlogged_jobs.json, in case an older
build of tailor_job.py produced resumes that were never logged.
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv, set_key

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
load_dotenv(ENV_PATH)

sys.path.insert(0, str(ROOT / "scripts"))
from gws_cli import gws

# Columns A-H predate v2 and keep their positions so existing rows stay aligned; v2 renamed
# "Fit Score" (1-10) to "Match %" -- rows logged before 2026-10-05 hold the old 8-10 scores.
HEADERS = ["Job Title", "Company", "Job Link", "Match %", "Resume Path", "Status", "Timestamp",
           "Company Notes", "Matched Keywords", "Keyword Gaps", "Source", "Fingerprint",
           # M-R added 2026-10-06 for Claude tailoring. Resume Path (E) and Resume Notes (R) are
           # written by Claude, never by this script.
           "Job Description", "Headline", "Company Logo", "Location", "Posted Date",
           "Resume Notes"]
HEADER_RANGE = "Sheet1!A1:R1"
MAX_CELL_CHARS = 45000   # Google Sheets rejects cells over 50,000 characters
SHEET_TITLE = "Job Application Tracker"
STATUS_OPTIONS = ["Not Applied", "Applied", "Interviewing", "Offer", "Rejected"]


def write_headers(sheet_id):
    """Idempotent: also upgrades a v1 sheet's header row to the v2 columns."""
    gws("sheets", "spreadsheets", "values", "update", "--params",
        json.dumps({"spreadsheetId": sheet_id, "range": HEADER_RANGE, "valueInputOption": "USER_ENTERED"}),
        "--json", json.dumps({"values": [HEADERS]}))


def get_or_create_sheet_id():
    import os
    sheet_id = os.environ.get("google_sheet_id", "").strip()
    if sheet_id:
        return sheet_id

    created = gws("sheets", "spreadsheets", "create", "--json",
                   json.dumps({"properties": {"title": SHEET_TITLE}}))
    sheet_id = created["spreadsheetId"]

    write_headers(sheet_id)

    gws("sheets", "spreadsheets", "batchUpdate", "--params",
        json.dumps({"spreadsheetId": sheet_id}),
        "--json", json.dumps({"requests": [{
            "setDataValidation": {
                "range": {
                    "sheetId": 0, "startRowIndex": 1, "endRowIndex": 1000,
                    "startColumnIndex": 5, "endColumnIndex": 6,
                },
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": v} for v in STATUS_OPTIONS],
                    },
                    "showCustomUi": True,
                    "strict": True,
                },
            }
        }]}))

    set_key(str(ENV_PATH), "google_sheet_id", sheet_id)
    print(f"Created new sheet: {SHEET_TITLE} ({sheet_id})")
    return sheet_id


JOB_ID_RE = re.compile(r"linkedin\.com/jobs/view/(?:[^/?#]*-)?(\d+)")


def link_key(link):
    """Stable dedup key derived from a job link, in the same `source:id` form sources use.

    LinkedIn stamps per-scrape tracking params (position/refId/trackingId) into every
    URL, so the same posting comes back with a different URL on every run -- deduping on
    the raw link would re-add every still-open job as a new row each day. The numeric job
    id in the path is stable across scrapes. Other boards fall back to the query-less URL.
    """
    match = JOB_ID_RE.search(link or "")
    return f"linkedin:{match.group(1)}" if match else (link or "").split("?")[0]


def norm_text(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def get_logged(sheet_id):
    """-> (job keys, fingerprints, legacy {(company, title)}) of every job already in the Sheet,
    i.e. every job that already has a resume.

    Precise matches: job key (same posting) and fingerprint (same company+title+description under
    a new id = a repost). Rows logged before the Fingerprint column existed have no fingerprint,
    so only those fall back to the coarse company+title match; a company's two different openings
    with the same title are therefore never merged once they have fingerprints."""
    result = gws("sheets", "+read", "--spreadsheet", sheet_id, "--range", "Sheet1!A:L")
    keys, fingerprints, legacy_titles = set(), set(), set()
    for row in result.get("values", [])[1:]:
        if len(row) > 2:
            keys.add(link_key(row[2]))
        fp = row[11].strip() if len(row) > 11 else ""
        if fp:
            fingerprints.add(fp)
        elif len(row) > 1:
            legacy_titles.add((norm_text(row[1]), norm_text(row[0])))
    return keys, fingerprints, legacy_titles


def canonical_link(job):
    """LinkedIn links carry per-scrape tracking params; store the clean, stable form."""
    match = JOB_ID_RE.search(job.get("link") or "")
    return f"https://www.linkedin.com/jobs/view/{match.group(1)}/" if match else job.get("link", "")


def cell(text, limit=MAX_CELL_CHARS):
    """Plain-text cell: a leading = + - @ would be parsed as a formula, so strip those."""
    text = str(text or "").strip()
    text = text.lstrip("=+-@ \t\r\n")
    return text[:limit]


def get_existing_keys(sheet_id):
    result = gws("sheets", "+read", "--spreadsheet", sheet_id, "--range", "Sheet1!C:C")
    values = result.get("values", [])
    return {link_key(row[0]) for row in values[1:] if row}


if __name__ == "__main__":
    import state

    # Qualified jobs from this run and any earlier run that never got logged.
    queue = state.load("pending_jobs.json", [])
    tailored_path = ROOT / "output" / "tailored_jobs.json"
    legacy = json.loads(tailored_path.read_text()) if tailored_path.exists() else []
    by_key = {}
    for j in state.load("unlogged_jobs.json", []) + \
            [j for j in legacy if j.get("status") == "saved"] + queue:
        by_key[j.get("key") or link_key(j["link"])] = j   # same job can be in several lists
    jobs = list(by_key.values())

    if not jobs:
        print("0 qualified jobs, nothing to log")
        raise SystemExit(0)

    sheet_id = get_or_create_sheet_id()
    write_headers(sheet_id)
    existing_keys = get_existing_keys(sheet_id)

    # "YYYY-MM-DD HH:MM:SS" Eastern (Modal runs in UTC) so Sheets parses it as a real datetime.
    logged_at = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S")
    new_rows, new_jobs = [], []
    for job in jobs:
        key = job.get("key") or link_key(job["link"])
        if key in existing_keys or link_key(job["link"]) in existing_keys:
            continue
        existing_keys.add(key)
        if not job.get("resume_link"):
            new_jobs.append({**job, "canonical_link": canonical_link(job)})
        new_rows.append([
            cell(job["title"]), cell(job["company"]), canonical_link(job),
            f"{job['match_pct']}%",
            job.get("resume_link") or "",          # Resume Path: Claude fills this in
            "Not Applied", logged_at,
            cell(job.get("company_notes", "")),
            cell(", ".join(m["keyword"] for m in job.get("matched_keywords", []))),
            cell(", ".join(job.get("gap_keywords", []))),
            job.get("source", ""),
            job.get("fingerprint", ""),
            cell(job.get("description", "")),
            cell(job.get("title_family") or job["title"]),
            job.get("company_logo") or "",
            cell(job.get("location", "")),
            cell(job.get("posted_date", "")),
            "",                                    # Resume Notes: Claude fills this in
        ])

    if new_rows:
        gws("sheets", "+append", "--spreadsheet", sheet_id, "--json-values", json.dumps(new_rows))
    # Tell Claude which rows need a resume (Drive "Claude Resumes/claude_queue.json").
    import claude_handoff
    claude_handoff.add_awaiting(new_jobs, logged_at)
    waiting = claude_handoff.publish_queue()
    print(f"{waiting} jobs waiting for a Claude resume (claude_queue.json updated)")
    # Everything is now in the Sheet (new rows, or already there): the queue is done.
    state.save("unlogged_jobs.json", [])
    state.save("pending_jobs.json", [])

    print(f"{len(jobs)} qualified jobs, {len(new_rows)} new rows added (resume pending for "
          f"Claude), {len(jobs) - len(new_rows)} already logged")
