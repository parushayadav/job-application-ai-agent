"""The job shape every source must return, so scoring/tailoring/sheet never care where a job
came from."""
import hashlib
import re


def fingerprint(company, title, description):
    """Identity of a posting independent of its board-assigned id. Boards give a repost a brand
    new id (LinkedIn does), so id-based dedup builds the same resume again; the same company +
    title + description is the same job."""
    def norm(text):
        return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()
    raw = f"{norm(company)}|{norm(title)}|{norm(description)[:3000]}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def make_job(*, source, source_id, title, company, link, description,
             posted_date=None, location=None, company_logo=None):
    return {
        "key": f"{source}:{source_id}",   # stable dedup key across runs and sources
        "source": source,
        "source_id": str(source_id),
        "title": title or "",
        "company": company or "",
        "link": link or "",
        "description": description or "",
        "posted_date": posted_date,
        "location": location,
        "company_logo": company_logo,
        "fingerprint": fingerprint(company, title, description),
    }
