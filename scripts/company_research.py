"""Company research (PRD 3.5, v2 4.7). Per qualified job, one OpenRouter call returning 3-5
interview talking points plus a short "company_focus" phrase.

Runs BEFORE tailoring (v2): the tailor uses company_focus for the one company-specific sentence
in the resume summary. talking points go to the Sheet only, never into the resume.

Uses a free OpenRouter model (no web-search grounding) -- talking points come from the model's
training data, not live/current news, so the prompt explicitly avoids asking for "recent news" to
keep the model from confidently hallucinating dates or events it can't actually verify.

Mutates the tailoring queue (STATE_DIR/pending_jobs.json) in place, adding company_notes and
company_focus.
"""
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

sys.path.insert(0, str(ROOT / "scripts"))
from openrouter import DailyQuotaExceeded, chat

MODEL = "nvidia/nemotron-3.5-lightning:free"

RESEARCH_PROMPT = """About the company __COMPANY__, for someone applying to a __TITLE__ role there.
Use only well-established, general facts. Do not mention specific recent news, dates, or events.
If you don't know the company, say so in the talking points and keep company_focus generic.

Respond with ONLY valid JSON, no markdown fences:
{"talking_points": ["3-5 short points: what the company does/its product, engineering culture or
tech stack if known, industry position, anything worth raising in an interview"],
 "company_focus": "<= 8 words naming what the company does, e.g. 'consumer banking and credit
cards' or 'streaming entertainment'"}"""


def research_company(company, title, api_key):
    prompt = RESEARCH_PROMPT.replace("__COMPANY__", company).replace("__TITLE__", title)
    result = chat(prompt, api_key, MODEL, timeout=60, json_mode=True)
    points = [str(p).strip() for p in result.get("talking_points", []) if str(p).strip()]
    return "\n".join(points[:5]), str(result.get("company_focus") or "").strip()


if __name__ == "__main__":
    import state

    api_key = os.environ["open_router_apikey"]
    # The tailoring queue (this run's qualified jobs + carry-overs; see score_jobs.py).
    jobs = state.load("pending_jobs.json", [])

    quota_event = threading.Event()

    def research_one(job):
        """Fills in the job (in place); returns True if it was researched."""
        if job.get("company_notes") or quota_event.is_set():
            return False
        try:
            job["company_notes"], job["company_focus"] = research_company(
                job["company"], job["title"], api_key)
            print(f"researched {job['company']}")
            return True
        except DailyQuotaExceeded as e:
            # Notes are nice-to-have context; leave the rest blank and let tailoring run.
            if not quota_event.is_set():
                quota_event.set()
                print(f"STOPPING research: {e}")
        except Exception as e:
            job["company_notes"], job["company_focus"] = "", ""
            print(f"ERROR researching {job['company']}: {e}")
        return False

    with ThreadPoolExecutor(max_workers=4) as pool:   # independent calls; rate cap is shared
        researched = sum(pool.map(research_one, jobs))

    state.save("pending_jobs.json", jobs)
    print(f"{researched} companies researched")
