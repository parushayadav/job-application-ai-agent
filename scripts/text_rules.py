"""Writing rules applied to everything that ends up in a resume.

No em dashes: they are the best-known tell of AI-generated text, and a recruiter who spots one
discounts the whole resume. Enforced at four layers so a single miss can't leak one through:
the base resume is written without them, the tailoring prompt forbids them, clean_dashes()
strips any that still appear (applied before render, to file names, and to model output), and
validate_resume.validate() rejects any resume that contains one.
"""
import re

EM_DASH = "—"
EN_DASH = "–"


def clean_dashes(text):
    """Replace em dashes with a comma (they separate clauses) and en dashes with a hyphen (they
    only ever appear in date ranges and labels here). Spacing around the replacement is tidied."""
    if not text:
        return text
    text = re.sub(rf"\s*{EM_DASH}\s*", ", ", text)
    text = text.replace(EN_DASH, "-")
    return re.sub(r",\s*,", ",", text)


def has_em_dash(text):
    return EM_DASH in (text or "")
