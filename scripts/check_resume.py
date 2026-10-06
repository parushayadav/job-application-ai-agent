"""Check a resume Claude tailored from a Sheet row (tailor-from-sheet skill, 2026-10-06).

Same gate as the automated path (validate_resume.validate_tailored): required sections, no em
dashes or placeholders, every matched JD keyword present, no gap keyword unless it is in the base
resume or skills inventory, role headings unchanged, no number/metric that isn't in the base
resume. Also prints the keyword coverage: of the JD technology keywords the Sheet row lists
(matched + gaps), how many appear in the resume.

    python3 scripts/check_resume.py <resume.md> --matched "Spark, Azure Databricks" \
        --gaps "Snowflake, dbt" [--base resume/base_resume.md]

Prints PASS/FAIL, the coverage line, and the reasons; exit code 1 on FAIL.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from inventory import build_index, contains_term, load_inventory, lookup
from validate_resume import validate_tailored


def split_list(text):
    return [k.strip() for k in (text or "").split(",") if k.strip()]


def check(resume_text, base_text, matched, gaps):
    index = build_index(load_inventory())
    # Gaps the candidate has since added to the inventory (e.g. MCP, dbt) count as matched now.
    now_matched = [g for g in gaps if lookup(g, index)]
    still_gaps = [g for g in gaps if not lookup(g, index)]
    keywords = matched + now_matched
    ok, reasons = validate_tailored(resume_text, base_text,
                                    [{"keyword": k, "skill": k} for k in keywords],
                                    still_gaps, index)
    all_terms = keywords + still_gaps
    present = [k for k in all_terms if contains_term(resume_text, k)]
    coverage = round(100 * len(present) / len(all_terms)) if all_terms else 100
    return ok, reasons, coverage, still_gaps


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("resume")
    parser.add_argument("--matched", default="")
    parser.add_argument("--gaps", default="")
    parser.add_argument("--base", default=str(ROOT / "resume" / "base_resume.md"))
    args = parser.parse_args()

    ok, reasons, coverage, still_gaps = check(
        Path(args.resume).read_text(encoding="utf-8"),
        Path(args.base).read_text(encoding="utf-8"),
        split_list(args.matched), split_list(args.gaps))
    print("PASS" if ok else "FAIL")
    print(f"Keyword coverage: {coverage}% of the JD's technology keywords"
          + (f" (not claimed, candidate lacks: {', '.join(still_gaps)})" if still_gaps else ""))
    for r in reasons:
        print(f"- {r}")
    sys.exit(0 if ok else 1)
