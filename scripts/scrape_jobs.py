"""Fetch new Data Engineer / Software Engineer postings from every enabled source (PRD v2 4.1-4.2).

- Window: only postings since the previous fetch (+1h overlap), capped at 24h.
- Budget: at most DAILY_FETCH_CAP (100) jobs fetched per Eastern day across all runs, at most
  PER_RUN_CAP per run -- this cap is what keeps Apify inside its free credit.
- Title filter + seen-job dedup happen here, before any (rate-limited) model call.

Writes output/raw_jobs.json.
"""
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "scripts"))

import state
from sources import SOURCES

PER_RUN_CAP = 34          # 3 runs/day x 34 ~= the 100/day cap
MIN_WINDOW_S = 3600
MAX_WINDOW_S = 24 * 3600
OVERLAP_S = 3600          # LinkedIn's posted time is coarse; overlap + dedup avoids gaps

# A title must name a relevant field AND be an engineer/developer role...
TITLE_INCLUDE = re.compile(
    r"\b(data|software|platform|cloud|etl|elt|big data|analytics|backend|back[- ]end|"
    r"python|spark|databricks|ai|ml|machine learning|integration|pipeline)\b.*\b(engineer|developer)\b"
    r"|\b(engineer|developer)\b.*\b(data|software|platform|cloud|etl|analytics|ai|ml)\b",
    re.IGNORECASE,
)
# ...and not be one of these look-alikes.
TITLE_EXCLUDE = re.compile(
    r"\b(sales|pre[- ]?sales|data entry|support engineer|field|network|civil|mechanical|"
    r"electrical|hardware|manufacturing|intern|internship|recruit\w*|teacher|instructor)\b",
    re.IGNORECASE,
)


def title_matches(title):
    return bool(TITLE_INCLUDE.search(title or "")) and not TITLE_EXCLUDE.search(title or "")


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

    seen = state.seen_keys()
    unique, keys = [], set()
    for job in fetched:
        if job["key"] in seen or job["key"] in keys:
            continue
        keys.add(job["key"])
        unique.append(job)
    relevant = [j for j in unique if title_matches(j["title"])]
    carried_keys = {j["key"] for j in carried}
    to_score = carried + [j for j in relevant if j["key"] not in carried_keys]

    out_path.write_text(json.dumps(to_score, indent=2))
    # Queue them durably right away: the fetch is already recorded (window + daily count moved
    # on), so if the run dies before scoring they must still be scored next run.
    # score_jobs.py rewrites this with only what it couldn't score.
    state.save("unscored_jobs.json", to_score)
    print(f"Fetched {len(fetched)} jobs, {len(fetched) - len(unique)} already seen, "
          f"{len(unique) - len(relevant)} dropped by title filter, {len(to_score)} to score "
          f"-> {out_path}  ({state.fetched_today()}/{state.DAILY_FETCH_CAP} fetched today)")
