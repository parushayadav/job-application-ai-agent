"""Pre-scoring filters (free, no model calls): which postings are even candidates.

Applied in scrape_jobs.py, before anything is scored or tailored.
"""
import re

# --- title: Data Engineer family only -------------------------------------------------------
# Must name a data discipline AND an engineer/developer role. "Software Engineer" alone does NOT
# match (excluded by request) -- but "Software Engineer, Data Platform" does, since it says data.
TITLE_INCLUDE = re.compile(
    r"\b(data|etl|elt|big data|databricks|spark|lakehouse|pipelines?)\b"
    r".{0,60}\b(engineer\w*|developer\w*|architect\w*)\b"
    r"|\b(engineer\w*|developer\w*)\b.{0,60}\b(data|etl|elt|big data|databricks|spark|lakehouse)\b",
    re.IGNORECASE,
)
TITLE_EXCLUDE = re.compile(
    r"\b(sales|pre[- ]?sales|data entry|support engineer|field|network|civil|mechanical|"
    r"electrical|hardware|manufacturing|intern|internship|recruit\w*|teacher|instructor|"
    r"analyst|scientist"
    # 2026-10-06: roles that name "data" but aren't Data Engineer jobs for an 8+ year IC
    r"|forward[- ]deployed|solutions?\s+(engineer|architect|consultant)|customer\s+engineer"
    r"|data\s+cent(er|re)|qa|quality\s+assurance|test\s+engineer|sdet"
    r"|ai\s+trainer|trainer|tutor|annotat\w*|label(l)?ing|freelance"
    r"|manager|director|head\s+of|vice\s+president|vp"
    r"|junior|jr|entry[- ]level|new\s+grad\w*|graduate|apprentice\w*)\b",
    re.IGNORECASE,
)


def title_matches(title):
    return bool(TITLE_INCLUDE.search(title or "")) and not TITLE_EXCLUDE.search(title or "")


# --- is the posting usable at all? ----------------------------------------------------------
MIN_DESCRIPTION_CHARS = 400   # shorter = a stub with nothing to tailor against
LINKEDIN_ID = re.compile(r"linkedin\.com/jobs/view/(?:[^/?#]*-)?\d+")


def unusable_reason(job):
    """None if the posting has what tailoring and applying need, else why it doesn't:
    a real job link, a company name, and a description long enough to tailor against."""
    link = job.get("link") or ""
    if job.get("source") == "linkedin" and not LINKEDIN_ID.search(link):
        return "no job link"
    if not link:
        return "no job link"
    if not (job.get("company") or "").strip():
        return "no company"
    if len((job.get("description") or "").strip()) < MIN_DESCRIPTION_CHARS:
        return "description too short"
    return None


# --- security clearance ---------------------------------------------------------------------
CLEARANCE = re.compile(
    r"top[\s-]*secret|\bts\s*/\s*sci\b|\bts\s+(required|clearance)|\bsecurity\s+clearance"
    r"|\b(secret|active|dod|dhs|government)\s+clearance|\bclearance\b|\bpolygraph\b",
    re.IGNORECASE,
)
NEGATION_BEFORE = re.compile(
    r"\b(no|not|without|neither|nor|never|n't|don't|doesn't|isn't|aren't)\b[^.\n]{0,50}$",
    re.IGNORECASE,
)
NEGATION_AFTER = re.compile(
    r"^[^.\n]{0,30}\b(not|n't)\s+(required|needed|necessary|a\s+requirement)",
    re.IGNORECASE,
)


def requires_clearance(title, description):
    """True if the posting asks for a security clearance. Mentions that are negated ("no security
    clearance required", "clearance is not needed") don't count. "Ability to obtain a clearance"
    does count -- the candidate has none, so the role is out either way."""
    for text in (title or "", description or ""):
        for m in CLEARANCE.finditer(text):
            before = text[max(0, m.start() - 60):m.start()]
            after = text[m.end():m.end() + 45]
            if not (NEGATION_BEFORE.search(before) or NEGATION_AFTER.search(after)):
                return True
    return False
