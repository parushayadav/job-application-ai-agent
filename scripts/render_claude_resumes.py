"""Turn Claude's tailored resume drafts into branded PDFs and log them (2026-10-06).

See claude_handoff.py for the whole flow. For every markdown draft in Drive
`Claude Resumes/_drafts`:
  1. download it and split the <!-- claude-resume --> header from the resume;
  2. status "flagged": just write Claude's notes into the Sheet row (no PDF);
     otherwise check the structure (validate_resume.validate), render the PDF with the accent
     color Claude chose (else the company logo color, else navy), at most 2 pages;
  3. upload the PDF to `Claude Resumes`, write its link into the row's "Resume Path" (col E)
     and the notes into "Resume Notes" (col R);
  4. move the draft to `_done` and drop the job from claude_queue.json.
A draft that fails stays in `_drafts` and is retried next time (its error goes to the log).

Runs on Modal at :55 past 5, 14 and 21 ET (after Claude's :15 run) and at the start of every
pipeline run.
"""
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "scripts"))

import claude_handoff as handoff
from gws_cli import gws, upload_file
from render_resume import render
from text_rules import clean_dashes
from validate_resume import validate
from write_sheet import get_or_create_sheet_id, link_key


def list_drafts():
    result = gws("drive", "files", "list", "--params", json.dumps({
        "q": f"'{handoff.DRAFTS_FOLDER_ID}' in parents and trashed = false",
        "fields": "files(id,name,createdTime)",
        "orderBy": "createdTime",
        "pageSize": 100,
    }))
    return [f for f in result.get("files", []) if f["name"].lower().endswith(".md")]


def download_text(file_id, workdir):
    # gws sandboxes -o to the current directory: write a relative name inside workdir.
    gws("drive", "files", "get", "--params", json.dumps({"fileId": file_id, "alt": "media"}),
        "-o", "draft.md", cwd=workdir)
    return (Path(workdir) / "draft.md").read_text(encoding="utf-8")


def move_to_done(file_id):
    gws("drive", "files", "update", "--params", json.dumps({
        "fileId": file_id, "addParents": handoff.DONE_FOLDER_ID,
        "removeParents": handoff.DRAFTS_FOLDER_ID, "fields": "id"}), "--json", "{}")


def sheet_rows_by_key(sheet_id):
    """job key -> 1-based Sheet row number, from the Job Link column."""
    result = gws("sheets", "+read", "--spreadsheet", sheet_id, "--range", "Sheet1!C:C")
    rows = {}
    for i, row in enumerate(result.get("values", []), start=1):
        if i > 1 and row:
            rows.setdefault(link_key(row[0]), i)
    return rows


def write_cell(sheet_id, cell, value):
    gws("sheets", "spreadsheets", "values", "update", "--params", json.dumps({
        "spreadsheetId": sheet_id, "range": f"Sheet1!{cell}", "valueInputOption": "RAW"}),
        "--json", json.dumps({"values": [[value]]}))


def safe_name(text):
    import re
    return re.sub(r"\s+", " ", re.sub(r'[<>:"/\\|?*]', "", text or "")).strip()


def process(draft, sheet_id, rows, workdir):
    text = download_text(draft["id"], workdir)
    meta, resume = handoff.parse_draft(text)
    key = meta.get("key", "")
    job = handoff.awaiting().get(key, {})
    row = rows.get(key) or rows.get(link_key(job.get("link", "")))
    if not row:
        raise ValueError(f"no Sheet row for {key or draft['name']}")
    now = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M")
    notes = clean_dashes(meta.get("notes", ""))

    if meta.get("status", "ready").lower() == "flagged":
        write_cell(sheet_id, f"R{row}", f"FLAGGED {now}: {notes}")
        return f"flagged ({notes})"

    ok, reason = validate(resume)
    if not ok:
        raise ValueError(f"draft failed validation: {reason}")
    title = safe_name(job.get("title") or meta.get("title") or "Data Engineer")
    company = safe_name(job.get("company") or meta.get("company") or "Company")
    resume_title = f"Chidvilas Parusha {title} Resume"
    pdf = Path(workdir) / "pdf" / f"Chidvilas Parusha - {company} - {title} Resume.pdf"
    accent, pages = render(resume, pdf, job.get("company_logo"), resume_title,
                           accent=meta.get("accent"))
    if pages > 2:
        raise ValueError(f"PDF is {pages} pages even after tightening")
    uploaded = upload_file(pdf, clean_dashes(pdf.name), handoff.RESUMES_FOLDER_ID, "application/pdf")
    write_cell(sheet_id, f"E{row}", uploaded["webViewLink"])
    write_cell(sheet_id, f"R{row}", f"Claude resume {now} | {pages}p | accent {accent}"
                                    + (f" | {notes}" if notes else ""))
    return f"saved ({pages}p, accent {accent})"


if __name__ == "__main__":
    drafts = list_drafts()
    if not drafts:
        print("No Claude drafts to render")
        handoff.publish_queue()
        raise SystemExit(0)

    sheet_id = get_or_create_sheet_id()
    rows = sheet_rows_by_key(sheet_id)
    done = failed = 0
    for draft in drafts:
        with tempfile.TemporaryDirectory() as workdir:
            try:
                outcome = process(draft, sheet_id, rows, workdir)
                key = handoff.parse_draft(
                    (Path(workdir) / "draft.md").read_text(encoding="utf-8"))[0].get("key", "")
                move_to_done(draft["id"])
                handoff.remove_awaiting(key)
                done += 1
                print(f"  {draft['name']}: {outcome}")
            except Exception as e:
                failed += 1
                print(f"  ERROR {draft['name']}: {e}")
    waiting = handoff.publish_queue()
    print(f"{len(drafts)} drafts: {done} done, {failed} failed (left in _drafts for retry), "
          f"{waiting} jobs still waiting for Claude")
    if failed and not done:
        sys.exit("every Claude draft failed to render -- see ERROR lines above")
