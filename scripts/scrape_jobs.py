"""Fetch new Data Engineer postings from every enabled source (PRD v2 4.1-4.2).

- Window: only postings since the previous fetch (+1h overlap), capped at 24h.
- Budget: at most DAILY_FETCH_CAP (100) jobs fetched per Eastern day across all runs, at most
  PER_RUN_CAP per run -- this cap is what keeps Apify inside its free credit.
- Free filters run here, before any (rate-limited) model call: already-seen id, repost of a job
  already seen (same company+title+description under a new id), title, unusable posting (no
  link or company, description under 400 characters), security clearance.
  Every filtered-out job is remembered too, so the overlap window can't pull it back in.

Writes output/raw_jobs.json.
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "scripts"))

import state
from filters import requires_clearance, title_matches, unusable_reason
from sources import SOURCES

PER_RUN_CAP = 34          # 3 runs/day x 34 ~= the 100/day cap
MIN_WINDOW_S = 3600
MAX_WINDOW_S = 24 * 3600
OVERLAP_S = 3600          # LinkedIn's posted time is coarse; overlap + dedup avoids gaps


def fetch_window_seconds():
    last = state.last_fetch_time()
    if last is None:
        return MAX_WINDOW_S
    elapsed = (state.now_utc() - last).total_seconds() + OVERLAP_S
    return int(min(MAX_WINDOW_S, max(MIN_WINDOW_S, elapsed)))


def enabled_sources():
    names = [n.strip() for n in os.environ.get("JOB_SOURCES", "linkedin").split(",") if n.strip()]
    unknown = [n for n in names if n not in SOURCES]
    if unknown:
        raise SystemExit(f"Unknown JOB_SOURCES: {unknown}. Known: {sorted(SOURCES)}")
    return names


if __name__ == "__main__":
    out_path = ROOT / "output" / "raw_jobs.json"
    out_path.parent.mkdir(exist_ok=True)

    # Jobs fetched earlier but not scored (quota hit / error) -- the window has moved past them.
    carried = state.load("unscored_jobs.json", [])
    if carried:
        print(f"{len(carried)} unscored jobs carried over from the previous run")

    budget = min(PER_RUN_CAP, state.DAILY_FETCH_CAP - state.fetched_today())
    if budget <= 0:
        out_path.write_text(json.dumps(carried, indent=2))
        print(f"Daily cap reached ({state.DAILY_FETCH_CAP} fetched today) -- nothing new to fetch")
        raise SystemExit(0)

    window = fetch_window_seconds()
    names = enabled_sources()
    print(f"Fetching up to {budget} jobs posted in the last {window / 3600:.1f}h from {names}")

    fetched = []
    per_source = max(1, budget // len(names))
    for name in names:
        fetched.extend(SOURCES[name](window, per_source))
    state.record_fetch(len(fetched))

    seen_keys, seen_fps = state.seen_keys(), state.seen_fingerprints()
    already_seen = reposts = wrong_title = clearance = unusable = 0
    relevant, dropped = [], []
    batch_keys, batch_fps = set(), set()
    for job in fetched:
        if job["key"] in seen_keys or job["key"] in batch_keys:
            already_seen += 1
            continue
        batch_keys.add(job["key"])
        if job["fingerprint"] in seen_fps or job["fingerprint"] in batch_fps:
            reposts += 1
            dropped.append(job)
            continue
        batch_fps.add(job["fingerprint"])
        if not title_matches(job["title"]):
            wrong_title += 1
            dropped.append(job)
        elif unusable_reason(job):
            unusable += 1
            dropped.append(job)
        elif requires_clearance(job["title"], job["description"]):
            clearance += 1
            dropped.append(job)
        else:
            relevant.append(job)
    state.mark_seen(dropped)   # filtered jobs are remembered too (as not qualified)
    carried_keys = {j["key"] for j in carried}
    to_score = carried + [j for j in relevant if j["key"] not in carried_keys]

    out_path.write_text(json.dumps(to_score, indent=2))
    # Queue them durably right away: the fetch is already recorded (window + daily count moved
    # on), so if the run dies before scoring they must still be scored next run.
    # score_jobs.py rewrites this with only what it couldn't score.
    state.save("unscored_jobs.json", to_score)
    print(f"Fetched {len(fetched)} jobs: {already_seen} already seen, {reposts} reposts of jobs "
          f"already seen, {wrong_title} not engineering titles, {unusable} unusable (no link, "
          f"company or description), {clearance} need a security "
          f"clearance -> {len(to_score)} to score -> {out_path}  "
          f"({state.fetched_today()}/{state.DAILY_FETCH_CAP} fetched today)")
