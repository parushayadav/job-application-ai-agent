"""Log successfully-tailored resumes to the "Job Application Tracker" Google Sheet.

Reads output/tailored_jobs.json (produced by the tailor-resume skill), appends one row
per status=="saved" job that isn't already logged (deduped by job link).
"""
import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv, set_key

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
load_dotenv(ENV_PATH)

HEADERS = ["Job Title", "Company", "Job Link", "Fit Score", "Resume Path", "Status", "Timestamp",
           "Company Notes"]
SHEET_TITLE = "Job Application Tracker"
STATUS_OPTIONS = ["Not Applied", "Applied", "Interviewing", "Offer", "Rejected"]


def _resolve_gws_command():
    gws_path = shutil.which("gws")
    if gws_path and gws_path.lower().endswith(".cmd"):
        # See scripts/format_resume_doc.py: npm's Windows .cmd shim routes through cmd.exe,
        # which Python's subprocess can't launch directly. Call the CLI's real JS entrypoint
        # through node.exe instead.
        run_js = Path(gws_path).parent / "node_modules" / "@googleworkspace" / "cli" / "run.js"
        if run_js.exists():
            return [shutil.which("node") or "node", str(run_js)]
    return [gws_path or "gws"]


GWS_CMD = _resolve_gws_command()


def gws(*args):
    result = subprocess.run([*GWS_CMD, *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gws {' '.join(args)} failed: {result.stderr}")
    return json.loads(result.stdout) if result.stdout.strip() else {}


def get_or_create_sheet_id():
    import os
    sheet_id = os.environ.get("google_sheet_id", "").strip()
    if sheet_id:
        return sheet_id

    created = gws("sheets", "spreadsheets", "create", "--json",
                   json.dumps({"properties": {"title": SHEET_TITLE}}))
    sheet_id = created["spreadsheetId"]

    gws("sheets", "spreadsheets", "values", "update", "--params",
        json.dumps({"spreadsheetId": sheet_id, "range": "Sheet1!A1:H1", "valueInputOption": "USER_ENTERED"}),
        "--json", json.dumps({"values": [HEADERS]}))

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


JOB_ID_RE = re.compile(r"/jobs/view/(?:[^/?#]*-)?(\d+)")


def job_key(link):
    """Stable dedup key for a job posting.

    LinkedIn stamps per-scrape tracking params (position/refId/trackingId) into every
    URL, so the same posting comes back with a different URL on every run -- deduping on
    the raw link would re-add every still-open job as a new row each day. The numeric job
    id in the path is stable across scrapes.
    """
    match = JOB_ID_RE.search(link or "")
    return match.group(1) if match else (link or "").split("?")[0]


def get_existing_keys(sheet_id):
    result = gws("sheets", "+read", "--spreadsheet", sheet_id, "--range", "Sheet1!C:C")
    values = result.get("values", [])
    return {job_key(row[0]) for row in values[1:] if row}


if __name__ == "__main__":
    tailored_jobs = json.loads((ROOT / "output" / "tailored_jobs.json").read_text())
    saved_jobs = [j for j in tailored_jobs if j.get("status") == "saved"]

    if not saved_jobs:
        print("0 saved jobs, nothing to log")
        raise SystemExit(0)

    sheet_id = get_or_create_sheet_id()
    existing_keys = get_existing_keys(sheet_id)

    # "YYYY-MM-DD HH:MM:SS" so Sheets parses it as a real datetime (sortable/filterable),
    # not just a date -- lets you see which run a row came from, not only which day.
    logged_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_rows = []
    for job in saved_jobs:
        key = job_key(job["link"])
        if key in existing_keys:
            continue
        existing_keys.add(key)
        resume_path = job.get("resume_link") or job.get("desktop_file", "")
        new_rows.append([
            job["title"], job["company"], job["link"],
            str(job["score"]), resume_path, "Not Applied", logged_at,
            job.get("company_notes", ""),
        ])

    if new_rows:
        gws("sheets", "+append", "--spreadsheet", sheet_id, "--json-values", json.dumps(new_rows))

    print(f"{len(saved_jobs)} saved jobs, {len(new_rows)} new rows added, "
          f"{len(saved_jobs) - len(new_rows)} already logged")
