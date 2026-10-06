"""Log successfully-tailored resumes to the "Job Application Tracker" Google Sheet.

Reads output/tailored_jobs.json (written by tailor_job.py or the tailor-resume skill), appends
one row per status=="saved" job that isn't already logged (deduped by `source:id` job key).
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
           "Company Notes", "Matched Keywords", "Keyword Gaps", "Source"]
HEADER_RANGE = "Sheet1!A1:K1"
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


def get_existing_keys(sheet_id):
    result = gws("sheets", "+read", "--spreadsheet", sheet_id, "--range", "Sheet1!C:C")
    values = result.get("values", [])
    return {link_key(row[0]) for row in values[1:] if row}


if __name__ == "__main__":
    import state

    tailored_path = ROOT / "output" / "tailored_jobs.json"
    tailored_jobs = json.loads(tailored_path.read_text()) if tailored_path.exists() else []
    # Plus anything an earlier run uploaded but was killed before logging (dedup below handles
    # overlap with this run's tailored_jobs.json).
    by_key = {}
    for j in state.load("unlogged_jobs.json", []) + \
            [j for j in tailored_jobs if j.get("status") == "saved"]:
        by_key[j.get("key") or link_key(j["link"])] = j   # same job can be in both lists
    saved_jobs = list(by_key.values())

    if not saved_jobs:
        print("0 saved jobs, nothing to log")
        raise SystemExit(0)

    sheet_id = get_or_create_sheet_id()
    write_headers(sheet_id)
    existing_keys = get_existing_keys(sheet_id)

    # "YYYY-MM-DD HH:MM:SS" Eastern (Modal runs in UTC) so Sheets parses it as a real datetime
    # (sortable/filterable) -- lets you see which run a row came from, not only which day.
    logged_at = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S")
    new_rows = []
    for job in saved_jobs:
        key = job.get("key") or link_key(job["link"])
        if key in existing_keys or link_key(job["link"]) in existing_keys:
            continue
        existing_keys.add(key)
        resume_path = job.get("resume_link") or job.get("desktop_file", "")
        new_rows.append([
            job["title"], job["company"], job["link"],
            f"{job['match_pct']}%", resume_path, "Not Applied", logged_at,
            job.get("company_notes", ""),
            ", ".join(m["keyword"] for m in job.get("matched_keywords", [])),
            ", ".join(job.get("gap_keywords", [])),
            job.get("source", ""),
        ])

    if new_rows:
        gws("sheets", "+append", "--spreadsheet", sheet_id, "--json-values", json.dumps(new_rows))
    state.save("unlogged_jobs.json", [])

    print(f"{len(saved_jobs)} saved jobs, {len(new_rows)} new rows added, "
          f"{len(saved_jobs) - len(new_rows)} already logged")
