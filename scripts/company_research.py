"""Company research (PRD 3.5). Per successfully-tailored job, one OpenRouter call returning
3-5 talking points -- context for the candidate, never written into the resume itself. Adds
a "company_notes" field to each saved entry in output/tailored_jobs.json.

Uses a free OpenRouter model (no web-search grounding, unlike a paid search-grounded model)
-- talking points come from the model's training data, not live/current news, so the prompt
explicitly avoids asking for "recent news" to keep the model from confidently hallucinating
dates or events it can't actually verify.
"""
import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "nvidia/nemotron-3.5-lightning:free"

RESEARCH_PROMPT = """Give 3-5 short talking points about __COMPANY__ useful for someone
interviewing for a __TITLE__ role there -- what the company does/its product, its engineering
culture or tech stack if known, its industry position, anything relevant to bring up in an
interview. Do not mention specific recent news, dates, or events unless you are certain they
are accurate -- stick to well-established, general facts about the company. Plain text, one
point per line, no headers, no commentary before or after."""


def research_company(company, title, api_key):
    prompt = RESEARCH_PROMPT.replace("__COMPANY__", company).replace("__TITLE__", title)
    resp = requests.post(
        OPENROUTER_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            # See score_jobs.py: this model's unbounded chain-of-thought can exhaust its
            # reasoning budget and return content: null instead of an answer.
            "reasoning": {"enabled": False},
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


if __name__ == "__main__":
    api_key = os.environ["open_router_apikey"]
    tailored_path = ROOT / "output" / "tailored_jobs.json"
    jobs = json.loads(tailored_path.read_text())

    researched = 0
    for job in jobs:
        if job.get("status") != "saved" or job.get("company_notes"):
            continue
        try:
            job["company_notes"] = research_company(job["company"], job["title"], api_key)
            researched += 1
            print(f"researched {job['company']}")
        except Exception as e:
            job["company_notes"] = ""
            print(f"ERROR researching {job['company']}: {e}")

    tailored_path.write_text(json.dumps(jobs, indent=2))
    print(f"{researched} companies researched")
