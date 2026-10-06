"""Job sources registry (PRD v2 4.1).

Every source module exposes `fetch(window_seconds, limit) -> list[dict]` returning jobs in the
shape built by `base.make_job`. To add a job board: write `sources/<board>.py` with that `fetch`,
add it below, and enable it via the JOB_SOURCES env var (comma-separated, default "linkedin").
Nothing downstream of scrape_jobs.py needs to change.
"""
from . import linkedin

SOURCES = {
    "linkedin": linkedin.fetch,
}
