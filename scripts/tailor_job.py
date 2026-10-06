"""Tailor the resume for each qualified job and deliver a branded PDF to Google Drive (PRD v2 4.5).

Automated-path equivalent of .claude/skills/tailor-resume/SKILL.md -- same rules, same
validator (validate_resume.validate_tailored), same renderer (render_resume.py) -- but driven by
a free OpenRouter model so it can run unattended on Modal.

The free model is NOT trusted to rewrite the resume: in testing it garbled whole sections
("AWS (EC2, S3 thoughts material minds)") and invented skills/years. So it only writes the
Summary and chooses the ORDER of existing bullets; everything else is assembled in code:
  - header from the base resume, with the job's title as headline
  - Skills: a "Core Skills" line with every matched JD keyword in the JD's own wording (ATS),
    then the base resume's categories, most relevant first, matched items first in each line
  - Experience / Projects: the base resume's bullets, verbatim, in the model's chosen order
  - Education / Certifications: verbatim
The Summary is checked (length, unknown words, validate_tailored), retried once with feedback,
and otherwise replaced by the base summary plus one company sentence.

Reads output/scored_jobs.json (qualified) + STATE_DIR/pending_jobs.json (earlier failures),
writes output/tailored_jobs.json.
"""
import json
import os
import re
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

sys.path.insert(0, str(ROOT / "scripts"))
import state
from gws_cli import create_folder, upload_file
from inventory import build_index, contains_term, load_inventory
from openrouter import DailyQuotaExceeded, chat
from render_resume import render
from validate_resume import validate_tailored

MODEL = "nvidia/nemotron-3.5-lightning:free"
MAX_PENDING_ATTEMPTS = 2
WORKERS = 3   # concurrent resumes (each renders a PDF in headless Chromium)
SUMMARY_WORDS = (40, 115)   # model part only; the company sentence is appended after
MAX_UNKNOWN_WORDS = 12  # summary words found in neither the base resume, JD, nor inventory

TAILOR_PROMPT = """You are tailoring a candidate's resume to a job posting. You do two things:

1. Write a new professional SUMMARY (3 sentences, 50-95 words):
   - Open with the candidate's real title and "8+ years" (keep that number exactly).
   - Weave in the most important of these JD keywords the candidate really has:
__MATCHED__
   - Do NOT mention the hiring company -- a closing sentence about it is added separately.
   - NEVER mention any of these (the candidate does not have them): __GAPS__
   - Only claim what the current summary or bullets below actually say. Do NOT add industries or
     domains (the candidate's are financial services, insurance, hospitality), leadership,
     mentoring, team sizes, or seniority words like "expert" that the resume doesn't state.
   - No other numbers, no tools outside the base resume and the list above. Plain prose.

2. ORDER the bullets of each role/project so the most relevant to this job come first. Use the
   bullet numbers shown below. Include every number exactly once.

Respond with ONLY valid JSON, no markdown fences:
{"summary": "...", "order": {"<role heading exactly as shown>": [3, 1, 2, ...], ...}}
__FEEDBACK__
CANDIDATE'S CURRENT SUMMARY:
__BASE_SUMMARY__

ROLES AND BULLETS:
__ROLES__

JOB TITLE: __TITLE__
COMPANY: __COMPANY__
JOB DESCRIPTION:
__DESCRIPTION__
"""

INVALID_FS_CHARS = re.compile(r'[<>:"/\\|?*]')


def sanitize_for_filesystem(text):
    """Strip characters Windows forbids in file/folder names, collapse whitespace."""
    cleaned = INVALID_FS_CHARS.sub("", text)
    return re.sub(r"\s+", " ", cleaned).strip()


# ---------- parsing the base resume ----------

def parse_resume(md):
    """-> {"header": [lines], "sections": [(title, body_lines)]}"""
    header, sections, current = [], [], None
    for line in md.strip().splitlines():
        if line.startswith("## "):
            current = (line[3:].strip(), [])
            sections.append(current)
        elif current is None:
            header.append(line)
        else:
            current[1].append(line)
    return {"header": header, "sections": sections}


def roles_in(body_lines):
    """Split a section body into [(heading, meta_lines, bullets)]."""
    roles, current = [], None
    for line in body_lines:
        if line.startswith("### "):
            current = (line[4:].strip(), [], [])
            roles.append(current)
        elif current is not None and line.startswith("- "):
            current[2].append(line[2:])
        elif current is not None and line.strip():
            current[1].append(line)
    return roles


def split_items(text):
    """Split a skills line on top-level commas: "Azure (A, B), AWS" -> ["Azure (A, B)", "AWS"]."""
    items, depth, buf = [], 0, ""
    for ch in text:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            items.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        items.append(buf.strip())
    return items


# ---------- deterministic assembly ----------

def build_skills(base_lines, matched, items_index_terms):
    """Core Skills line (JD wording) + base categories ordered by relevance."""
    def relevant(text):
        return any(contains_term(text, t) for t in items_index_terms)

    lines = []
    if matched:
        lines.append("- Core Skills for This Role: " + ", ".join(m["keyword"] for m in matched))
    scored_lines = []
    for line in base_lines:
        if not line.startswith("- "):
            continue
        label, sep, rest = line[2:].partition(":")
        if not sep:
            scored_lines.append((0, line))
            continue
        items = split_items(rest)
        hits = [i for i in items if relevant(i)]
        ordered = hits + [i for i in items if i not in hits]
        scored_lines.append((len(hits), f"- {label.strip()}: {', '.join(ordered)}"))
    scored_lines.sort(key=lambda pair: -pair[0])  # stable: ties keep base order
    return lines + [line for _, line in scored_lines]


def apply_order(bullets, order):
    """Reorder by 1-based indexes; ignore bad/duplicate indexes, append anything left out."""
    picked, seen = [], set()
    for n in order or []:
        if isinstance(n, int) and 1 <= n <= len(bullets) and n not in seen:
            seen.add(n)
            picked.append(bullets[n - 1])
    return picked + [b for i, b in enumerate(bullets, 1) if i not in seen]


def assemble(base, job, summary, orders):
    parsed = parse_resume(base)
    header = list(parsed["header"])
    headline = job.get("title_family") or job["title"]
    if len(header) > 1 and headline:
        header[1] = headline

    match_terms = set()
    for m in job["matched_keywords"]:
        match_terms.update([m["keyword"], m["skill"]])

    out = header + [""]
    for title, body in parsed["sections"]:
        out.append(f"## {title}")
        if title == "Summary":
            out.append(summary)
        elif title == "Skills":
            out += build_skills(body, job["matched_keywords"], match_terms)
        elif title in ("Experience", "Projects"):
            for heading, meta, bullets in roles_in(body):
                out += ["", f"### {heading}", *meta]
                out += [f"- {b}" for b in apply_order(bullets, orders.get(heading))]
        else:
            out += [l for l in body if l.strip()]
        out.append("")
    return "\n".join(out).strip() + "\n"


# ---------- model part: summary + bullet order ----------

def base_summary(base):
    for title, body in parse_resume(base)["sections"]:
        if title == "Summary":
            return " ".join(l.strip() for l in body if l.strip())
    return ""


def roles_block(base):
    out = []
    for title, body in parse_resume(base)["sections"]:
        if title in ("Experience", "Projects"):
            for heading, _, bullets in roles_in(body):
                out.append(f"### {heading}")
                out += [f"  {i}. {b}" for i, b in enumerate(bullets, 1)]
    return "\n".join(out)


def summary_problems(summary, job, base, inventory_words):
    """Cheap sanity checks the validator doesn't cover: length and unknown-word garbage."""
    words = re.findall(r"[A-Za-z][A-Za-z'+#-]*", summary)
    problems = []
    if not SUMMARY_WORDS[0] <= len(words) <= SUMMARY_WORDS[1]:
        problems.append(f"summary is {len(words)} words; must be {SUMMARY_WORDS[0]}-{SUMMARY_WORDS[1]}")
    known = " ".join([base, job["description"], job["title"], job["company"],
                      job.get("company_focus") or "", inventory_words]).lower()
    known_words = set(re.findall(r"[a-z][a-z'+#-]*", known))
    unknown = {w for w in (x.lower() for x in words) if w not in known_words}
    if len(unknown) > MAX_UNKNOWN_WORDS:
        problems.append(f"summary uses too many words unrelated to the resume/JD: "
                        f"{', '.join(sorted(unknown)[:15])}")
    return problems


def company_sentence(job):
    """The per-company personal touch, written in code so it is always present and always
    phrased as an aspiration (the model wrote things like "Partnering with <company>", which
    reads as if the candidate already works there)."""
    focus = (job.get("company_focus") or "").strip().rstrip(".")
    company = job["company"].strip()
    possessive = f"{company}'" if company.endswith("s") else f"{company}'s"
    where = f"{possessive} work in {focus}" if focus else f"{possessive} data platforms"
    return f"Looking to bring this experience to {where}."


LABEL_PREFIX = re.compile(r"\b(final sentence|summary|sentence \d)\s*:\s*", re.IGNORECASE)


def ask_model(job, base, api_key, feedback=""):
    prompt = (
        TAILOR_PROMPT
        .replace("__MATCHED__", "\n".join(f"     - {m['keyword']}" for m in job["matched_keywords"]))
        .replace("__GAPS__", ", ".join(job["gap_keywords"]) or "(none)")
        .replace("__FEEDBACK__", f"\nYOUR PREVIOUS ANSWER WAS REJECTED. Fix these:\n{feedback}\n"
                 if feedback else "")
        .replace("__BASE_SUMMARY__", base_summary(base))
        .replace("__ROLES__", roles_block(base))
        .replace("__TITLE__", job["title"])
        .replace("__COMPANY__", job["company"])
        .replace("__DESCRIPTION__", job["description"][:12000])
    )
    result = chat(prompt, api_key, MODEL, timeout=180, json_mode=True)
    summary = re.sub(r"\s+", " ", str(result.get("summary") or "")).strip()
    summary = LABEL_PREFIX.sub("", summary)  # model sometimes echoes prompt labels
    orders = result.get("order") if isinstance(result.get("order"), dict) else {}
    return summary, orders


def fallback_summary(job, base):
    return f"{base_summary(base)} {company_sentence(job)}"


def tailor_validated(job, base, index, inventory_words, api_key):
    """-> (markdown, mode, reasons). mode: "tailored" (model summary + order), "fallback" (base
    summary, model order if any), or None if even the fallback fails validation."""
    feedback, reasons, orders = "", [], {}
    for _ in range(2):
        summary, orders = ask_model(job, base, api_key, feedback)
        reasons = summary_problems(summary, job, base, inventory_words)
        text = assemble(base, job, f"{summary} {company_sentence(job)}", orders)
        ok, more = validate_tailored(text, base, job["matched_keywords"], job["gap_keywords"], index)
        reasons += more
        if not reasons:
            return text, "tailored", None
        feedback = "\n".join(f"- {r}" for r in reasons)

    text = assemble(base, job, fallback_summary(job, base), orders)
    ok, fallback_reasons = validate_tailored(text, base, job["matched_keywords"],
                                             job["gap_keywords"], index)
    if ok:
        return text, "fallback", reasons
    return None, None, reasons + fallback_reasons


def inventory_vocabulary(items):
    return " ".join(term for i in items for term in [i["name"], *i["aliases"]])


# ---------- delivery ----------

def deliver(job, text, parent_folder_id, tailored_dir, tmp_dir):
    safe_company = sanitize_for_filesystem(job["company"])
    safe_title = sanitize_for_filesystem(job["title"])
    folder_name = f"{safe_company} - {safe_title}"
    resume_title = f"Chidvilas Parusha {safe_title} Resume"

    # Unique per job (not per company+title): two postings can share both, and jobs now run
    # concurrently, so a shared path would have them overwrite each other.
    unique = sanitize_for_filesystem(job["key"])
    (tailored_dir / f"{folder_name} ({unique}).md").write_text(text, encoding="utf-8")
    pdf_path = tmp_dir / unique / f"{resume_title}.pdf"
    accent, pages = render(text, pdf_path, job.get("company_logo"), resume_title)

    folder_id, folder_link = create_folder(folder_name, parent_folder_id)
    uploaded = upload_file(pdf_path, f"{resume_title}.pdf", folder_id, "application/pdf")
    return folder_link, uploaded["webViewLink"], accent, pages


SHEET_FIELDS = ("key", "source", "title", "company", "link", "match_pct", "matched_keywords",
                "gap_keywords", "company_notes", "fingerprint")

if __name__ == "__main__":
    api_key = os.environ["open_router_apikey"]
    parent_folder_id = os.environ["google_drive_folder_id"]
    base_text = (ROOT / "resume" / "base_resume.md").read_text(encoding="utf-8")
    items = load_inventory()
    index, inventory_words = build_index(items), inventory_vocabulary(items)

    # score_jobs.py queues every qualified job in pending_jobs.json, so the queue covers this
    # run's jobs plus any left over from a run that failed or was killed part-way.
    queue = state.load("pending_jobs.json", [])
    this_run = {j["key"] for j in json.loads((ROOT / "output" / "scored_jobs.json").read_text())}
    carried = sum(1 for j in queue if j["key"] not in this_run)
    if carried:
        print(f"{carried} jobs carried over from earlier runs")

    tailored_dir = ROOT / "output" / "tailored"
    tailored_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.gettempdir()) / "tailor_job"

    results, quota_event = [], threading.Event()
    lock = threading.Lock()                       # guards results, remaining, and state files
    remaining = {j["key"]: j for j in queue}      # jobs still owed a resume -> pending_jobs.json

    def settle(job, row, requeue=None):
        """Record a job's outcome and checkpoint. `requeue` keeps it queued for the next run."""
        with lock:
            results.append(row)
            if requeue is not None:
                remaining[job["key"]] = requeue
            else:
                remaining.pop(job["key"], None)
            if row["status"] == "saved":
                # Uploaded but not yet in the Sheet -- write_sheet.py logs and clears these, so a
                # run killed before the Sheet step still gets its rows logged next time.
                state.save("unlogged_jobs.json", state.load("unlogged_jobs.json", []) + [row])
            # Checkpoint after every job: if the run is killed now, finished jobs aren't redone.
            state.save("pending_jobs.json", list(remaining.values()))

    def tailor_one(job):
        label = f"{job['company']} - {job['title']}"
        if quota_event.is_set():
            return  # stays in `remaining`
        try:
            text, mode, reasons = tailor_validated(job, base_text, index, inventory_words, api_key)
            if text is None:
                print(f"FLAGGED {label}: {'; '.join(reasons)}")
                settle(job, {**job, "status": "flagged_validation_failed",
                             "reason": "; ".join(reasons)})
                return
            if mode == "fallback":
                print(f"  {label}: model summary rejected twice ({'; '.join(reasons)}) "
                      f"-- using base summary")
            folder_link, resume_link, accent, pages = deliver(
                job, text, parent_folder_id, tailored_dir, tmp_dir)
            settle(job, {**{k: job.get(k) for k in SHEET_FIELDS},
                         "drive_folder_link": folder_link, "resume_link": resume_link,
                         "tailoring": mode, "status": "saved"})
            print(f"SAVED {label} ({job['match_pct']}% match, {mode}, {pages}p, accent {accent})")
        except DailyQuotaExceeded as e:
            if not quota_event.is_set():
                quota_event.set()
                print(f"STOPPING tailoring: {e}")
        except Exception as e:
            attempts = job.get("tailor_attempts", 0) + 1
            print(f"ERROR {label}: {e}")
            settle(job, {**job, "status": "flagged_error", "reason": str(e)},
                   requeue={**job, "tailor_attempts": attempts}
                   if attempts < MAX_PENDING_ATTEMPTS else None)

    # Each resume = one model call (+ retry), a PDF render and two Drive calls, all independent
    # of the others, so run a few at once. WORKERS is kept small: each render is a Chromium.
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(tailor_one, queue))

    still_pending = list(remaining.values())
    quota_error = "OpenRouter daily limit reached" if quota_event.is_set() else None
    state.save("pending_jobs.json", still_pending)
    (ROOT / "output" / "tailored_jobs.json").write_text(json.dumps(results, indent=2))

    saved = sum(1 for r in results if r["status"] == "saved")
    flagged = sum(1 for r in results if r["status"] == "flagged_validation_failed")
    errored = sum(1 for r in results if r["status"] == "flagged_error")
    print(f"{len(queue)} to tailor, {saved} saved, {flagged} failed validation, {errored} errors, "
          f"{len(still_pending)} queued for next run")

    # If every job hit an error (e.g. an expired Google token), the run produced nothing --
    # fail loudly so the Telegram alert fires instead of a "run complete" that hides it.
    if queue and saved == 0 and (errored or quota_error):
        sys.exit(f"no resumes saved: {quota_error or 'all jobs errored -- see ERROR lines above'}")
