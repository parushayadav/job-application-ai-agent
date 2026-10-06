"""Shared resume validation logic (PRD 3.4, v2 4.5). Used by both the interactive
Claude Code hook (.claude/hooks/resume_hook.py) and the automated
tailor_job.py script, so the two paths can't drift apart.

- validate(content): structural check (sections present, no placeholders). This is all the
  PreToolUse hook can run, since it only sees the file being written.
- validate_tailored(...): the full v2 gate -- structural + keyword coverage + no-fabrication
  guard + facts-unchanged check. The interactive path runs it via the CLI below; the automated
  path calls it directly.

CLI:  python scripts/validate_resume.py <tailored.md> <job_key>
      (job_key as in output/scored_jobs.json, e.g. linkedin:4012345678)
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from text_rules import has_em_dash

REQUIRED_SECTIONS = ["## Summary", "## Skills", "## Experience"]
PLACEHOLDER_MARKERS = ["[placeholder]", "todo", "tbd", "lorem ipsum", "{{", "}}"]
NUMBER_TOKEN = re.compile(r"\d[\d,.\-]*(?:[KMB]\+?|%|\+)?")


def validate(content):
    """Returns (ok: bool, reason: str | None)."""
    missing_sections = [s for s in REQUIRED_SECTIONS if s not in content]
    if missing_sections:
        return False, f"missing required section(s): {', '.join(missing_sections)}"

    if has_em_dash(content):
        return False, ("contains an em dash, which reads as AI-generated; use a comma, period, "
                       "colon or hyphen instead")

    lower_content = content.lower()
    found_placeholders = [m for m in PLACEHOLDER_MARKERS if m in lower_content]
    if found_placeholders:
        return False, f"placeholder text found: {', '.join(found_placeholders)}"

    return True, None


def _body(md):
    """Everything after the name/headline/contact block -- the headline legitimately changes
    per job (and may contain numbers like "Data Engineer II")."""
    idx = md.find("\n## ")
    return md[idx:] if idx >= 0 else md


def validate_tailored(content, base_text, matched_keywords, gap_keywords, inventory_index):
    """Returns (ok, reasons). matched_keywords: [{"keyword", "skill"}]; gap_keywords: [str]."""
    from inventory import contains_term, lookup

    reasons = []
    ok, reason = validate(content)
    if not ok:
        reasons.append(reason)

    missing = [m["keyword"] for m in matched_keywords if not contains_term(content, m["keyword"])]
    if missing:
        reasons.append(f"matched JD keywords missing from resume: {', '.join(missing)}")

    # A gap keyword may appear only if the candidate's real material already contains it.
    fabricated = [g for g in gap_keywords
                  if contains_term(content, g) and not contains_term(base_text, g)
                  and not lookup(g, inventory_index)]
    if fabricated:
        reasons.append(f"claims skills not in base resume or inventory: {', '.join(fabricated)}")

    for role in re.findall(r"^### .+$", base_text, re.MULTILINE):
        if role not in content:
            reasons.append(f"role heading changed or removed: {role[4:]}")

    # Version numbers inside matched keywords ("Python 3", "ADLS Gen2") are JD wording, not metrics.
    allowed = set(NUMBER_TOKEN.findall(base_text))
    for m in matched_keywords:
        allowed |= set(NUMBER_TOKEN.findall(m["keyword"]))
    new_numbers = set(NUMBER_TOKEN.findall(_body(content))) - allowed
    if new_numbers:
        reasons.append(f"numbers/metrics not in base resume: {', '.join(sorted(new_numbers))}")

    return not reasons, reasons


if __name__ == "__main__":
    from inventory import build_index, load_inventory

    md_path, job_key = sys.argv[1], sys.argv[2]
    jobs = json.loads((ROOT / "output" / "scored_jobs.json").read_text())
    job = next((j for j in jobs if j["key"] == job_key), None)
    if job is None:
        sys.exit(f"job {job_key} not in output/scored_jobs.json")
    ok, reasons = validate_tailored(
        Path(md_path).read_text(encoding="utf-8"),
        (ROOT / "resume" / "base_resume.md").read_text(encoding="utf-8"),
        job["matched_keywords"], job["gap_keywords"], build_index(load_inventory()),
    )
    if ok:
        print("PASS")
    else:
        print("FAIL\n- " + "\n- ".join(reasons))
        sys.exit(1)
