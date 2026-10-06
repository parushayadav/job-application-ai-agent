"""Persistent pipeline state that must survive between runs (PRD v2 4.2).

Modal containers are wiped after every run, so on Modal STATE_DIR points at the
`job-apply-agent-state` Volume (mounted at /state). Locally it defaults to ./state (gitignored).

Files:
  run_state.json     last successful fetch time + fetched-per-day counts (the 100/day cap)
  seen_jobs.json     job key -> outcome, so a posting is never scored/tailored twice
  pending_jobs.json  qualified jobs whose tailoring/upload failed, retried next run
  keyword_gaps.json  gap keyword counts (rendered to keyword_gaps.md by keyword_gaps.py)
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = Path(os.environ.get("STATE_DIR") or ROOT / "state")
EASTERN = ZoneInfo("America/New_York")

DAILY_FETCH_CAP = 100


def _path(name):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / name


def load(name, default):
    path = _path(name)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save(name, data):
    path = _path(name)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def now_utc():
    return datetime.now(timezone.utc)


def today_eastern():
    return now_utc().astimezone(EASTERN).strftime("%Y-%m-%d")


def fetched_today():
    return load("run_state.json", {}).get("fetched_by_day", {}).get(today_eastern(), 0)


def record_fetch(count):
    """Add to today's fetched count and stamp the fetch time (start of next run's window)."""
    run_state = load("run_state.json", {})
    by_day = run_state.get("fetched_by_day", {})
    by_day[today_eastern()] = by_day.get(today_eastern(), 0) + count
    # Only the last week matters; keep the file small.
    run_state["fetched_by_day"] = dict(sorted(by_day.items())[-7:])
    run_state["last_fetch_utc"] = now_utc().isoformat()
    save("run_state.json", run_state)


def last_fetch_time():
    value = load("run_state.json", {}).get("last_fetch_utc")
    return datetime.fromisoformat(value) if value else None


def seen_keys():
    return set(load("seen_jobs.json", {}))


def seen_fingerprints():
    return {v["fp"] for v in load("seen_jobs.json", {}).values() if v.get("fp")}


def mark_seen(jobs, outcome_field="qualified"):
    seen = load("seen_jobs.json", {})
    stamp = today_eastern()
    for job in jobs:
        seen[job["key"]] = {"date": stamp, "qualified": bool(job.get(outcome_field)),
                            "fp": job.get("fingerprint")}
    save("seen_jobs.json", seen)
