"""Turn Claude's tailored resume drafts into Word files and log them (2026-10-06).

See claude_handoff.py for the whole flow. For every markdown draft in Drive
`Claude Resumes/_working/_drafts`:
  1. download it and split the <!-- claude-resume --> header from the resume;
  2. status "flagged" or no resume body: use the base resume (job title as headline), so no
     row is left without a resume; then check the structure (validate_resume.validate), build the Word file
     (build_docx.py: Calibri, company color, <= 2 pages) and score it (ats_check.py);
  3. upload it to `Claude Resumes/<YYYY-MM-DD> - <Company> - <Title>/Chidvilas Parusha <Title> Resume.docx`
     and fill the job's row: Resume Path (clickable path to the file), ATS Score, Resume Notes;
  4. move the draft to `_done` and drop the job from claude_queue.json.
A draft that fails stays in `_drafts` and is retried next time (its error goes to the log).

Runs on Modal at :55 past 5, 14 and 21 ET (after Claude's :15 run) and at the start of every
pipeline run.
"""
import json
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "scripts"))

import ats_check
import claude_handoff as handoff
from build_docx import build_fitted
from gws_cli import create_folder, gws, upload_file
from text_rules import clean_dashes
from validate_resume import validate
from write_sheet import COL, get_or_create_sheet_id, link_key

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
CANDIDATE = "Chidvilas Parusha"
EASTERN = ZoneInfo("America/New_York")


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


def write_cells(sheet_id, row, values):
    """values: {header name: value}. USER_ENTERED so the HYPERLINK formula becomes a link."""
    for header, value in values.items():
        gws("sheets", "spreadsheets", "values", "update", "--params", json.dumps({
            "spreadsheetId": sheet_id, "range": f"Sheet1!{COL[header]}{row}",
            "valueInputOption": "USER_ENTERED"}),
            "--json", json.dumps({"values": [[value]]}))


def find_child(parent_id, name, folder=False):
    """Id of the newest file (or folder) with exactly this name in parent_id, else None."""
    kind = "=" if folder else "!="
    q = (f"'{parent_id}' in parents and trashed = false and name = '{name.replace(chr(39), chr(92) + chr(39))}'"
         f" and mimeType {kind} 'application/vnd.google-apps.folder'")
    files = gws("drive", "files", "list", "--params", json.dumps({
        "q": q, "fields": "files(id)", "orderBy": "createdTime desc", "pageSize": 1})).get("files", [])
    return files[0]["id"] if files else None


def job_from_meta(meta):
    """A job that already left the queue (e.g. re-tailored by hand): the draft header carries
    title, company, link, jd (one line), matched and gaps (comma separated)."""
    split = lambda v: [x.strip() for x in (v or "").split(",") if x.strip()]
    return {"title": meta.get("title", ""), "headline": meta.get("headline", ""),
            "company": meta.get("company", ""), "link": meta.get("link", ""),
            "description": meta.get("jd", ""), "matched_keywords": split(meta.get("matched")),
            "gap_keywords": split(meta.get("gaps"))}


def base_resume_for(title, workdir):
    """The base resume from Drive, with its headline (line 2) replaced by the job title."""
    gws("drive", "files", "get", "--params", json.dumps(
        {"fileId": handoff.BASE_RESUME_FILE_ID, "alt": "media"}), "-o", "base.md", cwd=workdir)
    lines = (Path(workdir) / "base.md").read_text(encoding="utf-8").splitlines()
    if len(lines) > 1 and lines[0].startswith("# "):
        lines[1] = clean_dashes(title)
    return "\n".join(lines) + "\n"


def safe_name(text, limit=80):
    text = re.sub(r"\s+", " ", re.sub(r'[<>:"/\\|?*]', "", text or "")).strip()
    return clean_dashes(text)[:limit].strip()


def notes_text(text):
    """A plain-text cell: no leading formula characters, no quotes that break HYPERLINK."""
    return clean_dashes(text or "").lstrip("=+-@ ").strip()


def process(draft, sheet_id, rows, workdir):
    text = download_text(draft["id"], workdir)
    meta, resume = handoff.parse_draft(text)
    key = meta.get("key", "")
    job = handoff.awaiting().get(key) or job_from_meta(meta)
    row = rows.get(key) or rows.get(link_key(job.get("link", "")))
    if not row:
        raise ValueError(f"no Sheet row for {key or draft['name']}")
    now = datetime.now(EASTERN)
    notes = notes_text(meta.get("notes", ""))

    if meta.get("status", "ready").lower() == "flagged" or not resume.strip():
        # Never leave a job without a resume (rule 2026-10-07): fall back to the base resume
        # with the job's title as the headline, and keep Claude's reason in the notes.
        resume = base_resume_for(job.get("headline") or job.get("title") or "Data Engineer",
                                 workdir)
        notes = notes_text(f"BASE RESUME (not tailored, review before submitting): {notes}")

    ok, reason = validate(resume)
    if not ok:
        raise ValueError(f"draft failed validation: {reason}")
    title = safe_name(job.get("headline") or job.get("title") or meta.get("title")
                      or "Data Engineer", 60)
    company = safe_name(job.get("company") or meta.get("company") or "Company", 50)
    doc_title = f"{CANDIDATE} {title} Resume"     # Word title property and file name
    file_name = f"{doc_title}.docx"
    folder_name = f"{now:%Y-%m-%d} - {company} - {title}"
    docx_path = Path(workdir) / file_name
    accent, pages, size = build_fitted(resume, docx_path, meta.get("accent"), doc_title)
    if pages is not None and pages > 2:
        raise ValueError(f"resume is {pages} pages even at the smallest layout")
    ats = ats_check.score(docx_path, job.get("description", ""), job.get("title") or title,
                          company, job.get("matched_keywords", []), job.get("gap_keywords", []),
                          pages)

    # Reuse a folder/file of the same name (e.g. placed by hand earlier) instead of duplicating.
    folder_id = find_child(handoff.RESUMES_FOLDER_ID, folder_name, folder=True)
    if not folder_id:
        folder_id, _ = create_folder(folder_name, handoff.RESUMES_FOLDER_ID)
    uploaded = upload_file(docx_path, file_name, folder_id, DOCX_MIME,
                           existing_id=find_child(folder_id, file_name))
    path_label = f"Claude Resumes/{folder_name}/{file_name}".replace('"', "'")
    status = "" if ats["passed"] else "BELOW 90, review before submitting. "
    write_cells(sheet_id, row, {
        "Resume Path": f'=HYPERLINK("{uploaded["webViewLink"]}", "{path_label}")',
        "ATS Score": ats["score"],
        "Resume Notes": notes_text(f"{status}{notes} | {ats_check.summary_line(ats)} | "
                                   f"{pages or '?'} pages, {size}pt, accent {accent}"),
    })
    return key, f"saved (ATS {ats['score']}, {pages}p, {size}pt)"


if __name__ == "__main__":
    drafts = list_drafts()
    if not drafts:
        print("No Claude drafts to build")
        handoff.publish_queue()
        raise SystemExit(0)

    sheet_id = get_or_create_sheet_id()
    rows = sheet_rows_by_key(sheet_id)
    done = failed = 0
    for draft in drafts:
        with tempfile.TemporaryDirectory() as workdir:
            try:
                key, outcome = process(draft, sheet_id, rows, workdir)
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
        sys.exit("every Claude draft failed -- see ERROR lines above")
