"""Build the tailored resume as an ATS-friendly Word file (2026-10-06, replaces the PDF for
Claude's resumes).

    python3 scripts/build_docx.py <resume.md> <out.docx> [--accent "#RRGGBB"] [--title TEXT]

Input is the same markdown every resume path uses (# name, headline, contact line, ## sections,
### roles with a date line, "- " bullets, "Skills:" lines). Output rules, chosen with Chidvilas:
- Times New Roman throughout (chosen by Chidvilas 2026-10-06; Garamond was tried and dropped
  because it ran to 3 pages in Word); name and section headings in the company's brand color
  (darkened for contrast), everything else black.
- ATS-safe structure: one column, real paragraphs, Word's own bullet list style, no tables,
  text boxes, images, headers or footers; contact details in the body; standard headings.
- At most 2 pages: tries progressively smaller font sizes / margins and keeps the first layout
  LibreOffice paginates to <= 2 pages. Liberation Serif (installed with LibreOffice, and on
  Modal via fonts-liberation) has Times New Roman's exact metrics, and every line has an exact
  height, so the count matches Word.
"""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from docx import Document
from docx.enum.text import WD_LINE_SPACING, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_resume import DEFAULT_ACCENT, HEX_COLOR, _readable
from text_rules import clean_dashes

FONT = "Times New Roman"
MAX_PAGES = 2
# (body pt, margin inches) from roomiest to tightest
LAYOUTS = [(11, 0.75), (10.5, 0.7), (10.5, 0.6), (10, 0.6), (10, 0.5), (9.5, 0.5)]
DATE_LINE = re.compile(r"\b(19|20)\d{2}\b|\bPresent\b", re.IGNORECASE)


def readable_accent(accent):
    if not (accent and HEX_COLOR.match(accent)):
        accent = DEFAULT_ACCENT
    rgb = _readable(tuple(int(accent[i:i + 2], 16) for i in (1, 3, 5)))
    return RGBColor(*rgb), "#{:02X}{:02X}{:02X}".format(*rgb)


def parse(md):
    """-> name, header lines (headline, contact...), [(section title, [lines])]"""
    name, header, sections, current = "", [], [], None
    for line in (l.rstrip() for l in md.splitlines()):
        if not line.strip():
            continue
        if line.startswith("# ") and not name:
            name = line[2:].strip()
        elif line.startswith("## "):
            current = (line[3:].strip(), [])
            sections.append(current)
        elif current is None:
            header.append(line.strip())
        else:
            current[1].append(line.strip())
    return name, header, sections


def _set_font(run, size, bold=False, italic=False, color=None):
    run.font.name = FONT
    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FONT)
    run.font.size = Pt(size)
    run.bold, run.italic = bold, italic
    if color is not None:
        run.font.color.rgb = color


def _add_runs(paragraph, text, size, color=None, italic=False, bold=False):
    """Plain text with **bold** spans."""
    for i, part in enumerate(re.split(r"\*\*(.+?)\*\*", text)):
        if part:
            _set_font(paragraph.add_run(part), size, bold=bold or bool(i % 2), italic=italic,
                      color=color)


LINE_HEIGHT = 1.15   # exact line height as a multiple of the font size


def _spacing(paragraph, before=0, after=0, size=None):
    """Exact line height (not "single"), so Word and LibreOffice lay out identical lines."""
    fmt = paragraph.paragraph_format
    fmt.space_before, fmt.space_after = Pt(before), Pt(after)
    if size:
        fmt.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        fmt.line_spacing = Pt(round(size * LINE_HEIGHT, 1))


def _bottom_border(paragraph, hex_color):
    p_pr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    for key, value in (("w:val", "single"), ("w:sz", "6"), ("w:space", "1"),
                       ("w:color", hex_color.lstrip("#"))):
        bottom.set(qn(key), value)
    borders.append(bottom)
    p_pr.append(borders)


def build(md_text, out_path, accent=None, title="Resume", body_pt=11, margin_in=0.75):
    md_text = clean_dashes(md_text)
    color, hex_color = readable_accent(accent)
    name, header, sections = parse(md_text)

    doc = Document()
    for section in doc.sections:
        section.top_margin = section.bottom_margin = Inches(margin_in)
        section.left_margin = section.right_margin = Inches(margin_in)
    normal = doc.styles["Normal"]
    normal.font.name, normal.font.size = FONT, Pt(body_pt)
    normal.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FONT)
    props = doc.core_properties
    props.title, props.author, props.subject = title, name.title(), "Resume"
    content_width = doc.sections[0].page_width - 2 * Inches(margin_in)

    p = doc.add_paragraph()
    _spacing(p, size=body_pt + 7)
    _add_runs(p, name, body_pt + 7, color=color, bold=True)
    if header:
        p = doc.add_paragraph()
        _spacing(p, size=body_pt + 1)
        _add_runs(p, header[0], body_pt + 1, bold=True)
    for line in header[1:]:
        p = doc.add_paragraph()
        _spacing(p, after=2, size=body_pt)
        _add_runs(p, line, body_pt - 0.5)

    for title_text, lines in sections:
        h = doc.add_paragraph()
        _spacing(h, before=7, after=3, size=body_pt + 1)
        h.paragraph_format.keep_with_next = True
        _add_runs(h, title_text.upper(), body_pt + 1, color=color, bold=True)
        _bottom_border(h, hex_color)
        is_skills = title_text.lower() == "skills"
        in_roles = title_text.lower() in ("experience", "projects")
        expect_date, role_par = False, None
        for line in lines:
            if line.startswith("### "):
                role_par = doc.add_paragraph()
                _spacing(role_par, before=5, size=body_pt)
                role_par.paragraph_format.keep_with_next = True
                _add_runs(role_par, line[4:], body_pt, bold=True)
                expect_date = True
            elif expect_date and DATE_LINE.search(line) and len(line) < 60:
                # Dates right-aligned on the role line via a tab stop (no tables: ATS-safe).
                role_par.paragraph_format.tab_stops.add_tab_stop(content_width,
                                                                 WD_TAB_ALIGNMENT.RIGHT)
                _set_font(role_par.add_run("\t" + line), body_pt)
                expect_date = False
            elif line.startswith("- "):
                text = line[2:]
                if is_skills and ":" in text:
                    p = doc.add_paragraph()
                    _spacing(p, after=1, size=body_pt)
                    label, _, rest = text.partition(":")
                    _set_font(p.add_run(label.strip() + ": "), body_pt, bold=True)
                    _add_runs(p, rest.strip(), body_pt)
                else:
                    p = doc.add_paragraph(style="List Bullet")
                    _spacing(p, after=1, size=body_pt)
                    _add_runs(p, text, body_pt)
            elif in_roles and line.lower().startswith("skills:"):
                p = doc.add_paragraph()
                _spacing(p, before=1, after=2, size=body_pt)
                _set_font(p.add_run("Skills: "), body_pt - 0.5, bold=True)
                _add_runs(p, line.split(":", 1)[1].strip(), body_pt - 0.5, italic=True)
            else:
                p = doc.add_paragraph()
                _spacing(p, after=2, size=body_pt)
                if in_roles:
                    p.paragraph_format.keep_with_next = True
                _add_runs(p, line, body_pt, italic=in_roles)
                expect_date = False
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path)
    return hex_color


def find_soffice():
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    return None


def to_pdf(docx_path, out_dir):
    """LibreOffice conversion (page counting, previews). -> PDF path or None."""
    soffice = find_soffice()
    if not soffice:
        return None
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run([soffice, f"-env:UserInstallation=file://{profile}/p", "--headless",
                        "--convert-to", "pdf", "--outdir", str(out_dir), str(docx_path)],
                       capture_output=True, text=True, timeout=180)
    pdf = Path(out_dir) / (Path(docx_path).stem + ".pdf")
    return pdf if pdf.exists() else None


def count_pages(docx_path):
    """Pages as LibreOffice lays the document out (None if LibreOffice isn't installed)."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = to_pdf(docx_path, tmp)
        if not pdf:
            return None
        return len(re.findall(rb"/Type\s*/Page(?![s\w])", pdf.read_bytes()))


def build_fitted(md_text, out_path, accent=None, title="Resume"):
    """Build with the roomiest layout that fits MAX_PAGES. -> (accent hex, pages, body pt)."""
    pages = hex_color = body_pt = None
    for body_pt, margin in LAYOUTS:
        hex_color = build(md_text, out_path, accent, title, body_pt, margin)
        pages = count_pages(out_path)
        if pages is None or pages <= MAX_PAGES:
            break
    return hex_color, pages, body_pt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("markdown")
    parser.add_argument("docx")
    parser.add_argument("--accent")
    parser.add_argument("--title", default="Resume")
    args = parser.parse_args()
    hex_color, pages, size = build_fitted(Path(args.markdown).read_text(encoding="utf-8"),
                                          args.docx, args.accent, args.title)
    print(f"Built {args.docx} ({pages if pages is not None else '?'} pages, {size}pt "
          f"{FONT}, accent {hex_color})")
