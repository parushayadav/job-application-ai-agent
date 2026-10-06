"""Score each new job by technology-keyword match against the skills inventory (PRD v2 4.3).

One model call per job extracts the JD's technology keywords and proposes which inventory skill
each one is. The model only *proposes*: code re-checks every proposed match against the real
inventory (so a hallucinated skill can't inflate the score), then computes
match_pct = matched / total and applies the >= MATCH_CUTOFF rule in code.

Reads output/raw_jobs.json, writes output/scored_jobs.json (qualified + rejected, so reject
counts stay auditable), marks every scored job as seen, and records gap keywords of qualified
jobs into keyword_gaps.
"""
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

sys.path.insert(0, str(ROOT / "scripts"))
import keyword_gaps
import state
from inventory import (appears_in, build_index, inventory_prompt_block, load_inventory, lookup,
                       normalize, plausible_alias)
from openrouter import DailyQuotaExceeded, chat
from tech_lexicon import TECH_TERMS
from write_sheet import get_logged, link_key, norm_text

MODEL = "nvidia/nemotron-3.5-lightning:free"
WORKERS = 4                # concurrent model calls (the request rate is capped separately)
MATCH_CUTOFF = 50          # percent
MIN_KEYWORDS = 3           # fewer concrete technologies than this = JD too vague to score

# Practices nearly every posting mentions. They still go on the resume (ATS reads them), but they
# say nothing about fit, so they're excluded from match %: on real postings, counting them made a
# Go/gRPC role at General Motors "70%" purely from Agile, Git, CI/CD and SQL.
GENERIC_TERMS = {normalize(t) for t in [
    "Agile", "Linux", "CI/CD", "Git", "Code Review", "ETL", "ELT", "Batch Processing",
    "Streaming ETL", "Data Modeling", "Data Warehousing", "Data Quality", "Data Governance",
    "Data Lineage", "Data Pipeline Monitoring", "REST APIs", "SQL", "NoSQL", "Cloud Migration",
    "Event-Driven Architecture", "Microservices", "Serverless", "Data Contracts", "Jira",
    "Confluence",
    # "uses AI coding assistants" lines -- workflow, not the role's stack
    "Claude", "OpenAI", "GitHub Copilot", "Copilot",
    # Vague phrases the model sometimes lists as "technologies" (they dragged a posting from
    # 90% to 67% as unfixable "gaps")
    "Data Pipelines", "Data Pipeline", "API Integration", "API Integrations", "APIs",
    "Performance Tuning", "Cloud Platforms", "Cloud Computing", "Big Data", "Data Engineering",
    "Data Analytics", "Machine Learning", "Distributed Systems", "Distributed Computing",
]}


def is_generic(keyword, skill=None):
    return normalize(skill or keyword) in GENERIC_TERMS or normalize(keyword) in GENERIC_TERMS
MAX_DESCRIPTION_CHARS = 12000

EXTRACT_PROMPT = """You are an ATS keyword analyst. Extract the technology keywords from a job
posting and match them to a candidate's skills inventory.

A keyword is a concrete technology, tool, platform, cloud service, programming language,
framework, database, or named technical practice (e.g. "Snowflake", "dbt", "Kubernetes",
"CI/CD", "Data Modeling", "Spark Structured Streaming"). NOT soft skills, degrees, years of
experience, industries, or vague words like "data", "cloud", "scalable".

Rules:
- Include required AND preferred keywords. Use the posting's own wording for "keyword".
- Max 30 keywords, no duplicates.
- "inventory_match" = the EXACT name of the inventory skill that is the SAME technology (an alias
  counts), else null. Related-but-different tools are NOT a match: Snowflake != BigQuery,
  Java != JavaScript, AWS Glue != Azure Data Factory, Kubernetes != Docker.
- "title_family" = the job title cleaned for a resume headline: drop requisition codes, team names
  and locations (e.g. "Data Engineer-Data Platforms-Google - 3" -> "Data Engineer").

Respond with ONLY valid JSON, no markdown fences:
{"title_family": "...", "keywords": [{"keyword": "...", "inventory_match": "..." or null}]}

CANDIDATE SKILLS INVENTORY:
__INVENTORY__

JOB TITLE: __TITLE__
COMPANY: __COMPANY__
JOB DESCRIPTION:
__DESCRIPTION__
"""


def is_keyword_shaped(keyword):
    """Drop sentence fragments the model sometimes returns as "keywords" ("Experience with
    cloud-based data platforms") -- they'd count as unfixable gaps and drag the match % down."""
    words = keyword.split()
    return (0 < len(words) <= 4 and len(keyword) <= 40
            and not keyword.lower().startswith(("experience", "knowledge", "familiarity",
                                                "understanding", "proficiency")))


def score_job(job, items, inventory_block, index, api_key):
    prompt = (
        EXTRACT_PROMPT
        .replace("__INVENTORY__", inventory_block)
        .replace("__TITLE__", job["title"])
        .replace("__COMPANY__", job["company"])
        .replace("__DESCRIPTION__", job["description"][:MAX_DESCRIPTION_CHARS])
    )
    result = chat(prompt, api_key, MODEL, timeout=120, json_mode=True)
    # Blank out the company's own name so "Oracle" the employer doesn't match Oracle the database.
    text = re.sub(re.escape(job["company"]), " ", f"{job['title']}\n{job['description']}",
                  flags=re.IGNORECASE) if job["company"] else f"{job['title']}\n{job['description']}"

    matched, gaps, accepted, matched_skills = [], [], [], set()

    def covered(term):
        """Already counted, as itself or as part of a longer accepted term ("Redshift" inside
        "Amazon Redshift") or vice versa."""
        n = f" {normalize(term)} "
        return any(n in f" {a} " or f" {a} " in n for a in accepted)

    def add_match(keyword, canonical):
        if canonical in matched_skills:  # "Glue" and "AWS Glue" are one skill, count once
            return
        matched_skills.add(canonical)
        matched.append({"keyword": keyword, "skill": canonical})
        accepted.append(normalize(keyword))

    def add_gap(keyword):
        if not covered(keyword):
            gaps.append(keyword)
            accepted.append(normalize(keyword))

    # 1. Deterministic scan (same answer every run): every inventory skill and every known
    #    non-inventory technology that literally appears in the posting. Longest terms first so
    #    "Azure Data Factory" wins over "Data Factory".
    for item in items:
        for term in sorted([item["name"], *item["aliases"]], key=len, reverse=True):
            if appears_in(text, term):
                add_match(term, item["name"])
                break
    for term in sorted(TECH_TERMS, key=len, reverse=True):
        if not lookup(term, index) and appears_in(text, term):
            add_gap(term)

    # 2. The model's extraction adds anything the lists above don't know about.
    for entry in result.get("keywords", []):
        keyword = str(entry.get("keyword") or "").strip()
        if not is_keyword_shaped(keyword) or covered(keyword):
            continue
        # Trust the JD and the inventory, not the model: the keyword must really be in the
        # posting (blocks padding the match with inventory skills the JD never asked for)...
        if not appears_in(text, keyword):
            continue
        # ...and must resolve to a real inventory skill, either directly or via a proposed
        # mapping that shares a meaningful word with that skill.
        canonical = lookup(keyword, index)
        proposed = lookup(entry.get("inventory_match"), index)
        if not canonical and proposed and plausible_alias(keyword, proposed, items):
            canonical = proposed
        if canonical:
            add_match(keyword, canonical)
        else:
            add_gap(keyword)

    tech_matched = [m for m in matched if not is_generic(m["keyword"], m["skill"])]
    tech_gaps = [g for g in gaps if not is_generic(g)]
    total = len(tech_matched) + len(tech_gaps)
    match_pct = round(100 * len(tech_matched) / total) if total else 0
    qualified = total >= MIN_KEYWORDS and match_pct >= MATCH_CUTOFF
    return {
        **job,
        "title_family": str(result.get("title_family") or job["title"]).strip(),
        "match_pct": match_pct,
        "matched_keywords": matched,
        "gap_keywords": gaps,
        "qualified": qualified,
        "reject_reason": None if qualified else (
            f"only {total} technology keywords" if total < MIN_KEYWORDS
            else f"{match_pct}% match < {MATCH_CUTOFF}%"),
    }


def drop_logged_in_sheet(jobs):
    """Dedup against the Sheet -- the durable record of which jobs already have a resume, which
    survives even if the Modal state Volume is lost. Same job id, same fingerprint (a repost), or
    -- only for rows predating the Fingerprint column -- same company + title."""
    sheet_id = os.environ.get("google_sheet_id", "").strip()
    if not sheet_id:
        return jobs
    try:
        logged_keys, logged_fps, legacy_titles = get_logged(sheet_id)
    except Exception as e:
        print(f"WARNING could not read Sheet for dedup: {e}")
        return jobs
    keep, dropped = [], []
    for j in jobs:
        if (j["key"] in logged_keys or link_key(j["link"]) in logged_keys
                or j.get("fingerprint") in logged_fps
                or (norm_text(j["company"]), norm_text(j["title"])) in legacy_titles):
            dropped.append(j)
        else:
            keep.append(j)
    if dropped:
        print(f"{len(dropped)} jobs skipped: already have a resume in the Sheet (same job or repost)")
        state.mark_seen(dropped)
    return keep


if __name__ == "__main__":
    api_key = os.environ["open_router_apikey"]
    items = load_inventory()
    index, inventory_block = build_index(items), inventory_prompt_block(items)
    jobs = drop_logged_in_sheet(json.loads((ROOT / "output" / "raw_jobs.json").read_text()))

    quota_event = threading.Event()

    def score_one(job):
        """-> ("ok", scored_job) | ("quota", job) | ("error", job). Never raises."""
        if quota_event.is_set():
            return "quota", job
        try:
            return "ok", score_job(job, items, inventory_block, index, api_key)
        except DailyQuotaExceeded as e:
            if not quota_event.is_set():
                quota_event.set()
                print(f"STOPPING scoring: {e}")
            return "quota", job
        except Exception as e:
            print(f"ERROR scoring {job['company']} - {job['title']}: {e}")
            return "error", job

    # Jobs are independent and the time is spent waiting on the model, so score several at once
    # (openrouter._throttle still keeps the combined request rate under the limit).
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        outcomes = list(pool.map(score_one, jobs))   # keeps input order

    scored, carry_over, errors = [], [], 0
    for status, job in outcomes:
        if status == "ok":
            scored.append(job)
        elif status == "quota":
            carry_over.append(job)
        else:
            errors += 1
            if job.get("score_attempts", 0) < 1:  # one more try next run, then give up
                carry_over.append({**job, "score_attempts": job.get("score_attempts", 0) + 1})
    quota_hit = quota_event.is_set()

    # The fetch window moves on, so a job not scored now would never be fetched again --
    # scrape_jobs.py prepends these to the next run.
    state.save("unscored_jobs.json", carry_over)
    (ROOT / "output" / "scored_jobs.json").write_text(json.dumps(scored, indent=2))
    state.mark_seen(scored)
    qualified = [j for j in scored if j["qualified"]]
    # Queue qualified jobs NOW (not after tailoring): they're already marked seen, so if the run
    # dies mid-tailoring they'd never be fetched again. tailor_job.py removes them once saved.
    pending = state.load("pending_jobs.json", [])
    pending_keys = {j["key"] for j in pending}
    state.save("pending_jobs.json", pending + [j for j in qualified if j["key"] not in pending_keys])
    keyword_gaps.write_markdown(keyword_gaps.record(qualified))

    for job in scored:
        verdict = "QUALIFIED" if job["qualified"] else f"rejected ({job['reject_reason']})"
        print(f"  {job['match_pct']:>3}%  {job['company']} - {job['title']}: {verdict}")
    print(f"{len(jobs)} to score, {len(scored)} scored, {len(qualified)} qualified "
          f"(>= {MATCH_CUTOFF}% keyword match), {len(scored) - len(qualified)} rejected, "
          f"{errors} errors, {len(carry_over)} carried to next run")

    if quota_hit and not scored:
        sys.exit(quota_hit)
    if jobs and errors == len(jobs):
        sys.exit("every job failed to score -- OpenRouter is down or the key/model is invalid")
