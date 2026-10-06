"""Track JD keywords that aren't in the skills inventory (PRD v2 4.4).

Counts live in STATE_DIR/keyword_gaps.json; keyword_gaps.md is regenerated from it every run.
Only qualified jobs (>= cutoff) feed the counts -- those are the roles actually being applied to,
so their gaps are the ones worth closing. Promotion into skills_inventory.md is a human decision:
this file only surfaces candidates, it never edits the inventory.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import state
from inventory import build_index, load_inventory, lookup, normalize

PROMOTION_THRESHOLD = 3
MD_NAME = "keyword_gaps.md"


def record(jobs):
    """Add each job's gap keywords to the running counts (one count per job per keyword)."""
    gaps = state.load("keyword_gaps.json", {})
    today = state.today_eastern()
    for job in jobs:
        for keyword in set(job.get("gap_keywords", [])):
            key = normalize(keyword)
            entry = gaps.setdefault(key, {"keyword": keyword, "count": 0, "first_seen": today,
                                          "last_seen": today, "companies": []})
            entry["count"] += 1
            entry["last_seen"] = today
            company = job.get("company", "")
            if company and company not in entry["companies"]:
                entry["companies"] = (entry["companies"] + [company])[-5:]
    state.save("keyword_gaps.json", gaps)
    return gaps


def render_markdown(gaps):
    # Anything since added to the inventory is no longer a gap -- hide it.
    index = build_index(load_inventory())
    open_gaps = [g for g in gaps.values() if not lookup(g["keyword"], index)]
    open_gaps.sort(key=lambda g: (-g["count"], g["keyword"].lower()))
    candidates = [g for g in open_gaps if g["count"] >= PROMOTION_THRESHOLD]

    def table(rows):
        if not rows:
            return "_None yet._\n"
        out = ["| Keyword | Jobs | Last seen | Recent companies |", "|---|---|---|---|"]
        out += [f"| {g['keyword']} | {g['count']} | {g['last_seen']} | {', '.join(g['companies'][-3:])} |"
                for g in rows]
        return "\n".join(out) + "\n"

    return (
        "# Keyword Gaps\n\n"
        "Auto-generated every run -- do not edit. Technologies that qualifying jobs asked for but\n"
        "that are **not** in `resume/skills_inventory.md`, so they were left off the resumes.\n\n"
        "To close a gap: if (and only if) you have genuinely used the tool, add it to\n"
        "`skills_inventory.md` and redeploy. From then on it counts as matched and appears on resumes.\n\n"
        f"Updated: {state.today_eastern()} | Open gaps: {len(open_gaps)}\n\n"
        f"## Promotion candidates (asked for by {PROMOTION_THRESHOLD}+ qualifying jobs)\n\n"
        "These are the gaps that would raise the match % of the most jobs. Worth adding to the\n"
        "inventory if you have the experience, or worth learning if you don't.\n\n"
        + table(candidates)
        + "\n## All open gaps\n\n"
        + table(open_gaps)
    )


def write_markdown(gaps):
    path = state.STATE_DIR / MD_NAME
    path.write_text(render_markdown(gaps), encoding="utf-8")
    return path


def upload_to_drive(parent_folder_id):
    """Mirror keyword_gaps.md into the Drive parent folder, overwriting the same file each run
    (its id is kept in run_state.json) so there's one always-current copy to open anywhere."""
    from gws_cli import upload_file

    path = write_markdown(state.load("keyword_gaps.json", {}))
    run_state = state.load("run_state.json", {})
    file_id = run_state.get("keyword_gaps_drive_id")
    try:
        result = upload_file(path, MD_NAME, parent_folder_id, "text/markdown", existing_id=file_id)
    except RuntimeError:
        if not file_id:
            raise
        # File was deleted from Drive by hand -- create a fresh one.
        result = upload_file(path, MD_NAME, parent_folder_id, "text/markdown")
    run_state = state.load("run_state.json", {})
    run_state["keyword_gaps_drive_id"] = result["id"]
    state.save("run_state.json", run_state)
    return result.get("webViewLink")


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    link = upload_to_drive(os.environ["google_drive_folder_id"])
    print(f"keyword_gaps.md -> Drive: {link}")
