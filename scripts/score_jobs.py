"""Score scraped jobs 1-10 against the base resume and apply the hard 8+ cutoff.

Reads output/raw_jobs.json, writes output/scored_jobs.json (qualified + rejected,
so reject counts stay auditable).
"""
import os
import json
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "nvidia/nemotron-3.5-lightning:free"
QUALIFY_CUTOFF = 8

RUBRIC_PROMPT = """You are screening a job posting against a candidate's resume for fit.

Score 1-10 using this rubric:
- Must-have skills/tools match (heaviest weight): does the resume cover the JD's explicitly
  listed required skills/tools?
- Years-of-experience fit: score down if the JD wants notably more experience than the resume
  shows, or if the JD's level signals a different seniority than the resume.
- Seniority/role-type match: e.g. IC DevOps/Cloud Infra vs SRE vs Platform vs a differently-scoped
  role (on-prem/networking-heavy, etc).
- Nice-to-haves: bonus signal only, never offsets a missing must-have.

Score bands:
9-10 = meets/exceeds nearly all must-haves and experience fits.
7-8 = meets most must-haves, close experience fit.
5-6 = roughly half the must-haves, or a real experience/seniority mismatch.
1-4 = missing most must-haves or a fundamentally different role.

Respond with ONLY valid JSON, no markdown fences, in this exact shape:
{"score": <int 1-10>, "reasoning": "<1-3 sentences>", "matched_must_haves": ["..."], "missing_must_haves": ["..."]}

RESUME:
__RESUME__

JOB TITLE: __TITLE__
COMPANY: __COMPANY__
JOB DESCRIPTION:
__DESCRIPTION__
"""


def score_job(job, resume_text, api_key):
    prompt = (
        RUBRIC_PROMPT
        .replace("__RESUME__", resume_text)
        .replace("__TITLE__", str(job.get("title")))
        .replace("__COMPANY__", str(job.get("company")))
        .replace("__DESCRIPTION__", str(job.get("description")))
    )
    resp = requests.post(
        OPENROUTER_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            # This model spends thousands of tokens on chain-of-thought before ever writing an
            # answer, and unbounded reasoning frequently exhausts its budget and returns
            # content: null (finish_reason "error") instead of the JSON. Disabling it gets a
            # direct, fast answer.
            "reasoning": {"enabled": False},
        },
        timeout=120,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    result = json.loads(content)

    return {
        **job,
        "score": result["score"],
        "reasoning": result["reasoning"],
        "matched_must_haves": result.get("matched_must_haves", []),
        "missing_must_haves": result.get("missing_must_haves", []),
        "qualified": result["score"] >= QUALIFY_CUTOFF,
    }


def score_jobs(jobs, resume_text, api_key):
    return [score_job(job, resume_text, api_key) for job in jobs]


if __name__ == "__main__":
    api_key = os.environ["open_router_apikey"]
    resume_text = (ROOT / "resume" / "base_resume.md").read_text()
    jobs = json.loads((ROOT / "output" / "raw_jobs.json").read_text())

    scored = score_jobs(jobs, resume_text, api_key)

    out_path = ROOT / "output" / "scored_jobs.json"
    out_path.write_text(json.dumps(scored, indent=2))

    qualified_count = sum(1 for j in scored if j["qualified"])
    print(f"{len(scored)} scraped, {qualified_count} qualified -> {out_path}")
