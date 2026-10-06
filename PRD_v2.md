# PRD v2 — Targeting, Keyword Matching, Branded Resumes, 3x Daily

Status: **Approved 2026-10-05, implemented.** Supersedes the v1 rules it names below; everything
else in `PRD.md` still holds.

Implementation notes beyond the draft (found while testing on real postings):
- **Software Engineer removed (2026-10-05, by request)** and **security-clearance roles excluded**
  (candidate has no clearance): `scripts/filters.py`, applied at fetch time. The whole fetch
  budget now goes to Data Engineer searches.
- **Repost dedup**: LinkedIn gives a repost a new id, so id-based dedup built duplicate resumes
  (EA, Publicis Sapient). Added a company+title+description fingerprint and a Sheet check on
  company+title, later made precise: the Sheet gets a `Fingerprint` column so only legacy rows fall
  back to company+title, and a company's distinct openings or the same role at different
  companies are never merged. Filtered-out jobs are remembered so they are never re-fetched into
  scoring.
- Scoring keeps only keywords that literally appear in the JD and model-proposed matches that
  share a meaningful word with the inventory skill (the model padded matches and mapped loosely,
  e.g. "coding assistants" -> "LLM Integration"). Sentence-fragment "keywords" are dropped.
- **Tailoring redesigned after reviewing real output.** The free model, asked to rewrite the
  whole resume, invented skills ("Amazon Redshift"), years ("13+"), a domain ("media"),
  "mentoring", and once garbled the Skills section into nonsense that still passed validation.
  So 4.5 changed: the model now writes only the Summary (3 sentences, gap list as "do not
  mention", no added domains/leadership) and the bullet ORDER. Code assembles the rest: header,
  a "Core Skills for This Role" line with every matched keyword in JD wording, base skill
  categories reordered by relevance, base bullets verbatim in the model's order, Education and
  Certifications verbatim, and a fixed company sentence ("Looking to bring this experience to
  {company}'s work in {focus}."). Summary is checked for length/unknown words + the validator,
  retried once, else the base summary is used.
- **Scoring made deterministic** after the first Modal run scored one posting 34% locally and
  100% on Modal (model omitted the gaps). Code now scans the JD for inventory skills and a
  ~150-term lexicon of common technologies; the model only adds terms beyond those. Generic
  practices (Agile, Git, CI/CD, SQL, ETL, Data Quality, AI-assistant mentions) go on the resume
  but don't count toward match % (they made a Go/gRPC role "70%"); the company's own name is
  ignored when scanning (Oracle the employer != Oracle DB). Minimum is now 3 concrete
  technologies instead of 5 keywords.
- **Crash safety**: the first Modal test was stopped mid-tailoring when the local client
  disconnected, which exposed that qualified jobs (already marked seen) would be lost. Qualified
  jobs now enter the retry queue at scoring time, tailoring checkpoints per job, and uploaded
  resumes not yet in the Sheet are logged on the next run.
- Renderer auto-tightens spacing to keep the resume at <= 2 pages.
- Jobs not scored/tailored in a run (quota, errors) carry over to the next run.

## 1. Goals (this phase only)

1. Target **Data Engineer** and **Software Engineer** roles (all title variants: Principal / Senior /
   AWS / Azure / Cloud / Platform / Big Data ... Data Engineer).
2. Qualify jobs by **technology/tool keyword match ≥ 50%** against a skills inventory, instead of
   the 1-10 fit score.
3. Put every JD keyword the candidate genuinely has into the resume (exact JD wording), and record
   every keyword they don't have in `keyword_gaps.md` for review.
4. Replace the plain Google-Docs PDF with an **ATS-safe, branded template** ("Classic accent"),
   themed with the hiring company's logo color plus a company-specific summary line.
5. Run **3x daily** (5:00, 14:00, 21:00 America/New_York), fetching only postings since the previous
   run, **max 100 fetched jobs/day**.
6. Make the job **source** pluggable so other job boards can be added later without touching the
   scoring/tailoring/sheet steps.

Non-goals this phase: new job boards (only the interface), auto-applying, paid models.

## 2. Decisions (from Q&A, 2026-10-05)

| Topic | Decision |
|---|---|
| Missing JD keywords | Never written into the resume. Logged to `keyword_gaps.md` with counts; repeated gaps are surfaced as "promotion candidates" that **you** confirm before they enter the inventory. |
| Daily cap | 100 **fetched** jobs/day across all runs. |
| Model | Keep free OpenRouter model (`nvidia/nemotron-3.5-lightning:free`). |
| Template | Classic accent, single column, company-colored. |

**Changed v1 hard rules:** "8+/10 cutoff" → "≥ 50% keyword match"; "Single niche: AI Data Engineer"
→ "Data Engineer + Software Engineer". **Unchanged:** no fabrication, no auto-submitting, Telegram
alert on failure.

## 3. Verified feasibility (tested before writing this)

| Risk | Check | Result |
|---|---|---|
| Fetch only "since last run" | Apify actor run with LinkedIn URL `f_TPR=r32400&sortBy=DD`, limit 5 | 5 jobs, all posted today. Custom windows work. |
| Exact 24h value | Actor input schema via API | `datePosted: past24Hours` exists (fallback). |
| Logo for theming | Actor output fields | Has `companyLogo` URL, plus `id`, `location`, `seniorityLevel`, `applyUrl`. |
| Branded PDF, ATS-safe | Prototype HTML → headless Chrome PDF, then text extraction | Renders well; text extracts in order. Found: letter-spaced headings extract as "SKI L LS" → template uses no letter-spacing. |
| Same renderer locally + Modal | Chrome/Edge present locally; Modal image adds Debian `chromium` | Same engine both paths. |

## 4. Design

### 4.1 Sources (pluggable)
```
scripts/sources/
  __init__.py      # SOURCES registry: {"linkedin": linkedin.fetch}
  base.py          # Job dataclass + fetch() contract
  linkedin.py      # Apify actor, URL mode with f_TPR window
```
- Contract: `fetch(window_seconds, limit) -> list[Job]`, `Job = {source, source_id, key, title,
  company, link, description, posted_date, location, company_logo}`; `key = f"{source}:{source_id}"`.
- `scrape_jobs.py` loops over enabled sources (`JOB_SOURCES=linkedin` env), splits the run budget.
  A new board = one new file + one registry line.
- LinkedIn searches: `Data Engineer` and `Software Engineer`, US, `sortBy=DD` (newest first),
  `f_TPR = seconds since last successful run + 1h overlap` (capped at 24h; 24h on first run).
- **Title pre-filter (free, before any model call):** keep titles matching data/software/platform/
  cloud/ETL/big-data + engineer/developer; drop obvious misses (e.g. "Data Entry", "Sales
  Engineer"). Logged as "N dropped by title filter".

### 4.2 Daily budget + persistent state (Modal Volume `job-apply-agent-state`)
Modal containers are wiped after each run, so state lives on a Volume (`STATE_DIR`; locally
`state/`, gitignored):
- `run_state.json` — last successful run time, `{date_ET: fetched_count}`.
- `seen_jobs.json` — every job key already processed (qualified or rejected) → no re-scoring,
  no re-tailoring across runs. Replaces the Sheet-only dedup.
- `keyword_gaps.json` + generated `keyword_gaps.md`.
- Per-run budget = `min(34, 100 − fetched_today)`; at 0 the run logs "daily cap reached" and exits OK.

### 4.3 Skills inventory + match % (replaces 1-10 scoring)
- `resume/skills_inventory.md` — seeded now by extracting every tool/technology from
  `base_resume.md`, grouped by category, with synonyms:
  `- Azure Data Lake Storage | ADLS, ADLS Gen2`. **You** add tools you've genuinely used.
- Per job, one model call: given JD + inventory, return `required_keywords` (tools/technologies
  only, canonical names) and for each: the inventory item it matches, or `null`.
- Code verifies every claimed match actually exists in the inventory (blocks model hallucination),
  then `match_pct = matched / required`. **Qualify if ≥ 50%.** Jobs with < 5 extracted keywords
  are treated as unscoreable (too vague) and rejected.
- Sheet's "Fit Score" column → "Match %"; new columns "Matched Keywords", "Keyword Gaps", "Source".

### 4.4 keyword_gaps.md
```
# Keyword Gaps   (auto-generated — edit skills_inventory.md, not this file)
## Promotion candidates (seen in ≥ 3 jobs)
| Keyword | Jobs | Last seen | Example companies |
| dbt     | 7    | 2026-10-05 | Capital One, Deloitte, ... |
## All gaps
...
```
- Each run adds that run's unmatched keywords (counts + last seen + up to 3 companies).
- Copied to the Drive parent folder each run so you can read it on your phone. Locally:
  `py -3.12 -m modal volume get job-apply-agent-state keyword_gaps.md resume/ --force`.
- To promote: add the keyword to `skills_inventory.md` **only if you have used it**, then
  `modal deploy`. Next runs count it as matched and it appears on resumes.

### 4.5 Tailoring
Same free model. Prompt inputs: base resume, matched keywords (JD wording ↔ inventory item),
company notes. Rules:
- Every matched keyword must appear in the resume, using the **JD's wording** where it's a
  synonym (JD says "ADLS Gen2", you have "Azure Data Lake Storage" → resume says "Azure Data Lake
  Storage (ADLS Gen2)").
- Inventory tools that aren't in the base resume go in **Skills only** (no invented bullets).
- Experience bullets: reorder + reword toward JD terms; never change employers, titles, dates,
  metrics.
- Summary: one sentence tying your real experience to the company's domain (personal touch).
- Headline under name = the JD's title family (e.g. "Senior Data Engineer").

Validation (`validate_resume.py`, shared by both paths), in addition to v1 checks:
1. **Coverage**: every matched keyword present → else fail.
2. **No fabrication guard**: any gap keyword present in output but absent from base resume +
   inventory → fail.
3. Employers / dates / metrics (numbers) from base resume unchanged → else fail.
On fail: **one retry** with the validator's reason fed back; second fail → `flagged`.

### 4.6 Branded template + PDF
- `templates/resume_classic.html` (Jinja-free: small Python renderer, no new heavy deps), bundled
  font (Source Sans 3, OFL) so local and Modal output match.
- Accent color: dominant non-white/non-grey color of `company_logo` (Pillow), darkened until
  contrast ≥ 4.5:1 on white for readability; fallback navy `#1F3A5F`.
- `scripts/render_resume.py md → html → pdf` via headless Chromium (Chrome/Edge locally, Debian
  `chromium` on Modal). Replaces Google Docs as the build step; `format_resume_doc.py` removed.
- PDF metadata title = "Chidvilas Parusha — {Job Title} Resume"; single page target, 2 max.

### 4.7 Pipeline order (Modal)
`scrape → score(match) → company_research (notes) → tailor+render → upload Drive → write_sheet →
update keyword_gaps + state`. Research moves before tailoring because the summary uses it.

### 4.8 Interactive path (Claude Code skill)
`tailor-resume` skill updated to the same rules, same validator, same `render_resume.py`; still
writes to the local Resume folder. Two paths stay separate per CLAUDE.md.

## 5. Schedule, limits, and what can break

Cron: `0 5,14,21 * * *`, `America/New_York` (one Modal cron, three firings).

| Resource | Limit | Our max usage/day | Verdict |
|---|---|---|---|
| Apify | $5/month free credit; actor ≈ $1 / 1,000 results | ≤ 100 results → ≈ $3/month | OK. The hard cap in code is what keeps it under. |
| OpenRouter free models | 1,000 req/day (with ≥ 10 credits), ~20 req/min | ≤ 100 match + ~3 per qualified (research, tailor, 1 retry) ≈ 250 worst case | OK. Client throttled to 15 req/min. |
| Modal Starter | $30/month credit | ~3 × 15 min, 1 CPU / 2 GB (Chromium) ≈ <$3/month | OK. Timeout raised 900s → 3600s. |
| Google APIs | Drive/Sheets per-minute quotas | ~2 calls per resume | OK. |

**Overlap:** runs are 7-9h apart and take ~10-20 min, so they can't collide; `max_containers=1` as a
guard anyway.

**How often can it run?** The binding limit is the 100 fetched/day cap (Apify cost), not the
platforms. 3x/day is comfortable; up to ~6x/day would also work with the same cap (each run just
gets a smaller share). More runs = fresher jobs, not more jobs.

**Known failure modes and handling:** Google token revoked → preflight fails fast + alert; OpenRouter
daily quota → stop calls, alert; Apify error/0 results → logged, run continues with 0 jobs (not a
failure); daily cap reached → clean exit. Telegram is **not configured yet**, so alerts only reach
you via Modal's email until you add `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`.

## 6. Build order + verification

| # | Step | Verify |
|---|---|---|
| 1 | Seed `skills_inventory.md` from base resume | You review it; every item traceable to the base resume |
| 2 | Sources package + LinkedIn URL mode + title filter + budget/state | Local run: N fetched ≤ budget, keys `linkedin:<id>`, filter counts logged |
| 3 | Match scoring + gaps file | Local run on fetched jobs: match % per job, ≥ 50% qualify, gaps.md generated |
| 4 | Template + renderer + logo color | Render 3 real companies; visual check + text extraction check |
| 5 | Tailoring rules + validator + retry | Coverage / no-fabrication checks pass; deliberate fabricated keyword is rejected |
| 6 | Sheet columns, Drive upload, gaps mirror | New rows show Match %, keywords, gaps; existing rows untouched |
| 7 | Modal: Volume, Chromium image, cron x3, timeout | `modal run` end-to-end; then `modal deploy` |
| 8 | Docs: PRD.md, CLAUDE.md, README, skill | Updated to v2 rules |

## 7. Open assumptions (correct me if wrong)
- Location stays **United States**, all workplace types (remote/hybrid/onsite) — LinkedIn's
  workplace filter is no longer supported by the actor as a URL filter.
- The existing Sheet keeps its old rows; header "Fit Score" is renamed "Match %" (old rows keep
  their 8-10 values).
- Jobs whose JD is mostly non-technical (< 5 tool keywords) are rejected rather than guessed.
