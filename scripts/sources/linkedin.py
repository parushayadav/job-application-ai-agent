"""LinkedIn via the Apify actor curious_coder/linkedin-jobs-scraper.

Uses search-URL mode rather than the actor's `datePosted` enum: LinkedIn's `f_TPR=r<seconds>` URL
filter accepts any window, so each run fetches only what was posted since the previous run
(the enum's smallest option is 24h, which would re-fetch -- and re-bill -- the same jobs on all
three daily runs). Billing is ~$1 per 1,000 results returned.
"""
import os
import re
from urllib.parse import urlencode

import requests

from .base import make_job

ACTOR_ID = "curious_coder~linkedin-jobs-scraper"
RUN_URL = f"https://api.apify.com/v2/acts/{ACTOR_ID}/run-sync-get-dataset-items"

# (keywords, share of the per-run budget). Most of the budget goes to Data Engineer; smaller
# searches catch adjacent engineering roles (2026-10-06), which must clear the stricter
# "other" lane in score_jobs.py (>= 60% match + >= 2 core data technologies in the JD).
SEARCHES = [
    ("Data Engineer", 0.55),
    ("Data Platform Engineer", 0.15),
    ("Forward Deployed Engineer", 0.15),
    ("AI Engineer", 0.15),
]
LOCATION = "United States"

JOB_ID_RE = re.compile(r"/jobs/view/(?:[^/?#]*-)?(\d+)")


def job_id_from_link(link):
    match = JOB_ID_RE.search(link or "")
    return match.group(1) if match else None


def _search_url(keywords, window_seconds):
    return "https://www.linkedin.com/jobs/search/?" + urlencode({
        "keywords": keywords,
        "location": LOCATION,
        "f_TPR": f"r{int(window_seconds)}",
        "sortBy": "DD",  # newest first, so a capped fetch keeps the freshest postings
    })


def _run_search(keywords, window_seconds, limit, api_key):
    resp = requests.post(
        RUN_URL,
        params={"token": api_key},
        json={
            "urls": [_search_url(keywords, window_seconds)],
            "limitPerSource": limit,
            "scrapeCompany": False,
        },
        timeout=600,
    )
    resp.raise_for_status()
    return resp.json()


def fetch(window_seconds, limit):
    api_key = os.environ["apify_api_key"]
    jobs, remaining = [], limit
    for i, (keywords, share) in enumerate(SEARCHES):
        if remaining <= 0:
            break
        # Last search gets whatever budget is left, so the full limit can be used.
        search_limit = remaining if i == len(SEARCHES) - 1 else max(1, round(limit * share))
        search_limit = min(search_limit, remaining)
        raw = _run_search(keywords, window_seconds, search_limit, api_key)
        remaining -= len(raw)
        jobs.extend(to_job(item) for item in raw)
        print(f"  linkedin '{keywords}': {len(raw)} jobs")
    return jobs


def to_job(item):
    link = item.get("link") or item.get("jobUrl") or ""
    return make_job(
        source="linkedin",
        source_id=item.get("id") or job_id_from_link(link) or link.split("?")[0],
        title=item.get("title"),
        company=item.get("companyName") or item.get("company"),
        link=link,
        description=item.get("descriptionText") or item.get("description"),
        posted_date=item.get("postedAt") or item.get("postedDate"),
        location=item.get("location"),
        company_logo=item.get("companyLogo"),
    )
