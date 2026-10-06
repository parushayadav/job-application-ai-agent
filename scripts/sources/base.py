"""The job shape every source must return, so scoring/tailoring/sheet never care where a job
came from."""


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
    }
