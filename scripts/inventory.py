"""Parse resume/skills_inventory.md and match keywords against it (PRD v2 4.3).

Format per line, under any `## Category` heading:  `- Canonical Name | synonym, synonym`
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INVENTORY_PATH = ROOT / "resume" / "skills_inventory.md"


def normalize(term):
    """Case/punctuation-insensitive form used for all comparisons ("Azure Data-Factory" ==
    "azure data factory")."""
    term = term.lower().replace("&", " and ")
    term = re.sub(r"[^a-z0-9+#/.]+", " ", term)
    return re.sub(r"\s+", " ", term).strip(" .")


def load_inventory(path=INVENTORY_PATH):
    """Returns [{"name", "aliases": [...], "category"}] in file order."""
    items, category = [], None
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("## "):
            category = line[3:].strip()
            continue
        if not category or not line.startswith("- "):
            continue
        name, _, aliases = line[2:].partition("|")
        name = name.strip()
        if not name:
            continue
        items.append({
            "name": name,
            "aliases": [a.strip() for a in aliases.split(",") if a.strip()],
            "category": category,
        })
    return items


def build_index(items):
    """normalized name/alias -> canonical name."""
    index = {}
    for item in items:
        for term in [item["name"], *item["aliases"]]:
            index.setdefault(normalize(term), item["name"])
    return index


def lookup(term, index):
    """Canonical inventory name for `term`, or None. Exact normalized match only -- fuzzy
    matching here is how "Java" would end up matching "JavaScript"."""
    if not term:
        return None
    return index.get(normalize(term))


GENERIC_WORDS = {"data", "and", "the", "of", "for", "with", "a", "an", "to", "in", "on",
                 "platform", "platforms", "tools", "tool", "services", "service", "advanced",
                 "pipelines", "pipeline", "systems", "experience", "frameworks", "framework"}


def _words(term):
    return {w for w in re.split(r"[^a-z0-9+#]+", term.lower()) if w and w not in GENERIC_WORDS}


def plausible_alias(keyword, canonical, items):
    """True if a model-proposed keyword -> skill mapping shares a meaningful word with the skill
    or one of its aliases. Blocks loose mappings like "coding assistants" -> "LLM Integration"
    while allowing "Advanced SQL" -> "SQL" or "data lake" -> "Azure Data Lake Storage"."""
    item = next((i for i in items if i["name"] == canonical), None)
    if item is None:
        return False
    keyword_words = _words(keyword)
    return any(keyword_words & _words(term) for term in [item["name"], *item["aliases"]])


def appears_in(text, keyword):
    """Keyword is really in the JD: whole-word match, or a match after normalizing punctuation
    ("Infrastructure-as-code" vs "infrastructure as code")."""
    if contains_term(text, keyword):
        return True
    norm_kw = normalize(keyword)
    return bool(norm_kw) and f" {norm_kw} " in f" {normalize(text)} "


def inventory_prompt_block(items):
    """Compact listing for the model: one line per skill with its aliases."""
    lines = []
    for item in items:
        alias = f" (also: {', '.join(item['aliases'])})" if item["aliases"] else ""
        lines.append(f"- {item['name']}{alias}")
    return "\n".join(lines)


def contains_term(text, term):
    """Whole-word, case-insensitive containment. Very short terms (<= 3 chars, e.g. "Ray",
    "dbt") and all-caps acronyms ("REST", "SAP", "RAG") are matched case-sensitively, so
    ordinary words ("the rest of the team") don't false-positive."""
    if not term:
        return False
    pattern = r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])"
    flags = 0 if len(term) <= 3 or term.isupper() else re.IGNORECASE
    return re.search(pattern, text, flags) is not None
