"""LinkedIn via the Apify actor curious_coder/linkedin-jobs-scraper.

Uses search-URL mode rather than the actor's `datePosted` enum: LinkedIn's `f_TPR=r<seconds>` URL
filter accepts any window, so each run fetches only what was posted since the previous run
(the enum's smallest option is 24h, which would re-fetch -- and re-bill -- the same jobs on all
three daily runs). Billing is ~$1 per 1,000 results returned.

Remote only (Chidvilas, 2026-10-22): every search carries LinkedIn's "Remote" workplace filter
(`f_WT=2`; 1 = on-site, 3 = hybrid are left out), so only remote postings are fetched, billed,
scored and given a resume. As a backstop, a posting the actor explicitly marks as on-site or
hybrid (workplace fields, or "(On-site)"/"(Hybrid)" in the location) is dropped in fetch().
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
WORKPLACE_REMOTE = "2"    # LinkedIn f_WT: 1 On-site, 2 Remote, 3 Hybrid (remote only, 2026-10-22)
NOT_REMOTE = re.compile(r"\b(on[- ]?site|onsite|hybrid)\b", re.IGNORECASE)

JOB_ID_RE = re.compile(r"/jobs/view/(?:[^/?#]*-)?(\d+)")


def job_id_from_link(link):
    match = JOB_ID_RE.search(link or "")
    return match.group(1) if match else None


def _search_url(keywords, window_seconds):
    return "https://www.linkedin.com/jobs/search/?" + urlencode({
        "keywords": keywords,
        "location": LOCATION,
        "f_TPR": f"r{int(window_seconds)}",
        "f_WT": WORKPLACE_REMOTE,
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
        remote = [item for item in raw if not explicitly_not_remote(item)]
        jobs.extend(to_job(item) for item in remote)
        dropped = len(raw) - len(remote)
        print(f"  linkedin '{keywords}' (remote only): {len(remote)} jobs"
              + (f", {dropped} dropped as on-site/hybrid" if dropped else ""))
    return jobs


def explicitly_not_remote(item):
    """True only when the actor's own data says the posting is on-site or hybrid. Unknown or
    missing workplace info keeps the job (the f_WT=2 search filter already asked for remote)."""
    if item.get("workRemoteAllowed") is False:
        return True
    workplace = item.get("workplaceTypes") or item.get("workplaceType") or item.get("workType")
    if isinstance(workplace, (list, tuple)):
        workplace = " ".join(str(w) for w in workplace)
    if workplace and NOT_REMOTE.search(str(workplace)) and "remote" not in str(workplace).lower():
        return True
    location = str(item.get("location") or "")
    return bool(re.search(r"\((on[- ]?site|hybrid)\)", location, re.IGNORECASE))


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
