---
name: tailor-resume
description: Tailor the base resume to each qualified Data Engineer / Software Engineer job in output/scored_jobs.json and deliver it as a branded, ATS-safe PDF in a per-job folder under the local Resume folder. Use when asked to tailor resumes, run the tailor-resume step, or generate resumes for qualifying jobs.
---

# Tailor Resume (interactive path, PRD v2)

Turns each qualified job in `output/scored_jobs.json` into a tailored, company-branded PDF saved
locally. Same rules, validator and renderer as the automated path (`scripts/tailor_job.py`) —
only the delivery differs (local folder instead of Drive).

Base output folder (all per-job folders are created directly inside this):
```
C:\Users\chidv\OneDrive\Documents\documents\docs new\Chidvilas Resume\Resume
```
In Git Bash / this project's Bash tool, address it as:
```
/c/Users/chidv/OneDrive/Documents/documents/docs new/Chidvilas Resume/Resume
```
Always double-quote it — the `docs new` segment has a space in it.

## Hard rule

**Never invent experience, employers, tools, dates, or metrics.** Only reorder and reword content
in `resume/base_resume.md`, plus skills listed in `resume/skills_inventory.md`. Each job's
`gap_keywords` are tools the candidate does NOT have — never mention them, even though the JD asks.
They are tracked in `keyword_gaps.md` for the human to review instead.

## Procedure

Read `output/scored_jobs.json`, filter to `qualified == true` (keyword match ≥ 50%; run
`scripts/score_jobs.py` first if the file is missing). Run `scripts/company_research.py` if jobs
lack `company_focus`. For each job, do all steps; if one fails, record it as flagged (step 7) and
move on.

1. Read `resume/base_resume.md` and the job's `matched_keywords` (`[{keyword, skill}]` — JD
   wording → the candidate's real skill), `gap_keywords`, `title_family`, `company_focus`.

2. Write the tailored resume in the same markdown structure as the base resume:
   - Header block copied exactly, except the line under `# Name` becomes `title_family`.
   - `## Summary`: 3 sentences leading with the real title, "8+ years" (exactly), and the top
     matched keywords — claiming only domains/responsibilities the base resume states — then the
     closing sentence `Looking to bring this experience to {company}'s work in {company_focus}.`
   - `## Skills`: first line `- Core Skills for This Role: ` + every matched keyword in the JD's
     wording (this is what guarantees ATS coverage), then the base resume's category lines,
     most relevant category first and JD-matched items first within each line. Nothing else.
   - `## Experience` / `## Projects`: keep every heading, date and location line exactly; **reorder
     bullets only, word for word** (same as the automated path — rewording is where fabrication
     and garbling crept in during testing).
   - `## Education`, `## Certifications`: copy unchanged.

3. Compute `safe_company` / `safe_title` (strip `< > : " / \ | ? *`, collapse whitespace), then
   `folder_name = f"{safe_company} - {safe_title}"` and
   `resume_title = f"Chidvilas Parusha {safe_title} Resume"`.

4. Write it to `output/tailored/{folder_name}.md` with the Write tool. The `PreToolUse` hook
   (`.claude/hooks/resume_hook.py`) blocks the write if required sections are missing or
   placeholder text remains — if blocked, fix and rewrite once, else flag the job.

5. Run the full v2 validator (keyword coverage, no-fabrication, facts unchanged):
   ```bash
   python3 scripts/validate_resume.py "output/tailored/{folder_name}.md" "{job key}"
   ```
   On `FAIL`, fix exactly the listed problems, rewrite (step 4) and re-validate once. A second
   failure → flag with `status: flagged_validation_failed` and the reasons.

6. Render the branded PDF straight into the job folder (accent color comes from the company logo):
   ```bash
   mkdir -p "/c/Users/chidv/OneDrive/Documents/documents/docs new/Chidvilas Resume/Resume/{folder_name}"
   python3 scripts/render_resume.py "output/tailored/{folder_name}.md" \
     "/c/Users/chidv/OneDrive/Documents/documents/docs new/Chidvilas Resume/Resume/{folder_name}/{resume_title}.pdf" \
     --logo "{company_logo}" --title "{resume_title}"
   ```
   Open the PDF and check it reads well (≤ 2 pages, no markdown symbols).

7. Append a record to `output/tailored_jobs.json` (create it as `[]` first if missing). Carry over
   `key, source, title, company, link, match_pct, matched_keywords, gap_keywords, company_notes`
   from the scored job and add:
   ```json
   {
     "desktop_folder": "C:\\Users\\chidv\\OneDrive\\Documents\\documents\\docs new\\Chidvilas Resume\\Resume\\{folder_name}",
     "desktop_file": "C:\\Users\\chidv\\OneDrive\\Documents\\documents\\docs new\\Chidvilas Resume\\Resume\\{folder_name}\\{resume_title}.pdf",
     "status": "saved"
   }
   ```
   Flagged jobs: `"status": "flagged_validation_failed"` plus `"reason"`, no desktop fields.

8. After all jobs, print `f"{qualified_count} qualified, {saved_count} saved, {flagged_count} flagged"`,
   then offer to run `python3 scripts/write_sheet.py` to log the saved ones.
