"""Check a cover letter Claude wrote for one job (tailor-from-sheet skill, 2026-10-22).

The same truthfulness gate as the resume, plus the cover-letter standards agreed with Chidvilas:

FAIL (must be fixed):
- no em/en dashes, no placeholders ([Company], TODO, ...);
- starts with a greeting ("Dear ...,") and ends with "Sincerely," + "Chidvilas Parusha";
- body of 230 to 380 words (target ~300; greeting and sign-off not counted), 4 to 5 paragraphs;
- names the company;
- no number or metric that is not in the base resume (same rule as the resume);
- no tool the candidate lacks (a JD gap keyword not in the base resume or inventory), unless the
  sentence naming it says how his own experience transfers (contains "transfer");
- no salary, visa, sponsorship or work-authorization talk (his choice: leave that to the form);
- no filler ("passionate", "results-driven", "leverag...", "spearhead...", ...);
- not a copy of the resume: no sentence of 12+ words taken word for word from the resume.
WARN (look at it): job title not named; Cleveland State master's or MBA not mentioned.

    python3 scripts/check_cover_letter.py <letter.md> --resume <resume.md> --company "Deloitte" \
        --title "Forward Deployed Engineer" --gaps "Palantir, Foundry"

Prints PASS/FAIL, the word count and the reasons; exit code 1 on FAIL.
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from inventory import build_index, contains_term, load_inventory, lookup
from text_rules import has_em_dash
from validate_resume import NUMBER_TOKEN, PLACEHOLDER_MARKERS

MIN_WORDS, MAX_WORDS = 230, 380
FILLER = ["passionate", "results-driven", "results driven", "proven track record", "synergy",
          "cutting-edge", "cutting edge", "leverag", "spearhead", "go-getter", "think outside",
          "hard-working", "hardworking", "team player", "to whom it may concern"]
FORBIDDEN_TOPICS = re.compile(r"\b(salary|compensation|visa|sponsor\w*|h-?1b|green card|"
                              r"work authori[sz]ation|authori[sz]ed to work)\b", re.IGNORECASE)
PLACEHOLDER_RE = re.compile(r"\[[^\]]*\]|<[^>]*>|\bXX+\b")


def split_list(text):
    return [k.strip() for k in (text or "").split(",") if k.strip()]


def paragraphs(letter):
    return [p.strip() for p in re.split(r"\n\s*\n", letter.strip()) if p.strip()]


def check(letter, resume, base, company, title, gaps):
    fails, warns = [], []
    paras = paragraphs(letter)
    if has_em_dash(letter):
        fails.append("contains an em or en dash: use a comma, colon or period")
    low = letter.lower()
    if any(m in low for m in PLACEHOLDER_MARKERS) or PLACEHOLDER_RE.search(letter):
        fails.append("contains a placeholder like [Company] or TODO")
    if not paras or not re.match(r"^Dear .+,$", paras[0]):
        fails.append('first line must be the greeting, e.g. "Dear Hiring Team,"')
    if not paras or not re.search(r"^Sincerely,\s*\nChidvilas Parusha$", paras[-1]):
        fails.append('must end with "Sincerely," and "Chidvilas Parusha" on the next line')
    body = paras[1:-1] if len(paras) > 2 else paras
    words = len(re.findall(r"[A-Za-z0-9][\w'+.#/%-]*", " ".join(body)))
    if not MIN_WORDS <= words <= MAX_WORDS:
        fails.append(f"body is {words} words; keep it between {MIN_WORDS} and {MAX_WORDS} (~300)")
    if not 4 <= len(body) <= 5:
        fails.append(f"body has {len(body)} paragraphs; use 4 (or 5)")
    if company and company.lower() not in low:
        fails.append(f'does not name the company "{company}"')
    if title and not any(w.lower() in low for w in re.findall(r"[A-Za-z]{4,}", title)
                         if w.lower() not in ("senior", "engineer")):
        warns.append(f'does not use the job title "{title}"')

    def numbers(text):   # "2026," and "300%." are 2026 and 300%
        return {n.rstrip(",.-") for n in NUMBER_TOKEN.findall(text)}
    new_numbers = sorted(numbers(" ".join(body)) - numbers(base))
    if new_numbers:
        fails.append(f"numbers not in the base resume: {', '.join(new_numbers)}")

    index = build_index(load_inventory())
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(body))
    for gap in gaps:
        if lookup(gap, index) or contains_term(base, gap):
            continue                                   # he has it after all
        for sentence in sentences:
            if contains_term(sentence, gap) and "transfer" not in sentence.lower():
                fails.append(f'names "{gap}", which he has not used; either leave it out or say '
                             f'in that sentence how his experience transfers to it')
                break

    if FORBIDDEN_TOPICS.search(letter):
        fails.append("mentions salary, visa, sponsorship or work authorization (leave those out)")
    hits = [f for f in FILLER if f in low]
    if hits:
        fails.append(f"filler words: {', '.join(hits)}")

    resume_sentences = {re.sub(r"\W+", " ", s).strip().lower()
                        for s in re.split(r"(?<=[.!?])\s+|\n", resume)}
    for sentence in sentences:
        norm = re.sub(r"\W+", " ", sentence).strip().lower()
        if len(norm.split()) >= 12 and any(norm in r for r in resume_sentences if r):
            fails.append(f'copied word for word from the resume: "{sentence[:70]}..."')
            break

    if "cleveland state" not in low:
        warns.append("Cleveland State master's (Computer and Information Science) not mentioned")
    if "mba" not in low and "business administration" not in low:
        warns.append("MBA not mentioned")
    return not fails, fails, warns, words


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("letter")
    parser.add_argument("--resume", required=True)
    parser.add_argument("--company", required=True)
    parser.add_argument("--title", default="")
    parser.add_argument("--gaps", default="")
    parser.add_argument("--base", default=str(ROOT / "resume" / "base_resume.md"))
    args = parser.parse_args()
    ok, fails, warns, words = check(
        Path(args.letter).read_text(encoding="utf-8"),
        Path(args.resume).read_text(encoding="utf-8"),
        Path(args.base).read_text(encoding="utf-8"),
        args.company, args.title, split_list(args.gaps))
    print("PASS" if ok else "FAIL")
    print(f"Body: {words} words")
    for f in fails:
        print(f"- {f}")
    for w in warns:
        print(f"- WARN: {w}")
    sys.exit(0 if ok else 1)
