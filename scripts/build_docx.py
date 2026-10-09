"""Build the tailored resume as an ATS-friendly Word file (2026-10-06, replaces the PDF for
Claude's resumes).

    python3 scripts/build_docx.py <resume.md> <out.docx> [--accent "#RRGGBB"] [--title TEXT]

Input is the same markdown every resume path uses (# name, headline, contact line, ## sections,
### roles with a date line, "- " bullets, "Skills:" lines). Output rules, chosen with Chidvilas:
- Calibri throughout (chosen by Chidvilas 2026-10-07, after Times New Roman and Garamond); name,
  section headings and each role's dates in the company's brand color (darkened for contrast),
  dates bold; everything else black.
- ATS-safe structure: one column, real paragraphs, Word's own bullet list style, no tables,
  text boxes, images, headers or footers; contact details in the body; standard headings.
- At most 2 pages, with page 2 well used (2026-10-08): tries progressively smaller font sizes /
  margins and keeps the roomiest layout that LibreOffice paginates to <= 2 pages with page 2 at
  most PAGE2_MAX full. That headroom absorbs small Word/LibreOffice layout differences (Word once
  showed a 3rd page). If page 2 is then under PAGE2_MIN full, spacing between bullets, roles and
  sections is stretched evenly until it is. Carlito (fonts-crosextra-carlito) has Calibri's exact
  metrics, every line has an exact height, and widow/orphan control is off (Word would otherwise
  move lines to the next page), so Word and LibreOffice lay out the same lines.
- to_pdf() makes the PDF that is delivered next to the Word file; it is the same LibreOffice
  layout that was measured, so it is always <= 2 pages.
- line_fill() reports bullets whose last line is mostly empty, so the wording can be adjusted to
  fill lines instead of wasting them (--fill-report on the command line).
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

FONT = "Calibri"
MAX_PAGES = 2
# (body pt, margin inches) from roomiest to tightest
LAYOUTS = [(11, 0.75), (11, 0.6), (10.5, 0.6), (10.5, 0.5), (10, 0.5), (9.5, 0.5)]
PAGE2_MAX = 0.93          # leave room on page 2 so Word never spills onto a 3rd page
PAGE2_MIN = 0.85          # below this, stretch spacing so page 2 does not end half empty
MAX_EXTRA_PT = 4.0        # most extra space added per bullet when stretching (pt)
BULLET_INDENT_IN = 0.25   # Word's "List Bullet" text indent in this template
# Carlito has Calibri's exact metrics: used by LibreOffice for the page count and by
# line_fill() to measure where each bullet's text wraps.
CARLITO_CANDIDATES = [
    "/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf",
    "/usr/share/fonts/crosextra/Carlito-Regular.ttf",
]
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
            if name.isupper():          # "CHIDVILAS PARUSHA" -> "Chidvilas Parusha" (his rule)
                name = name.title()
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


def build(md_text, out_path, accent=None, title="Resume", body_pt=11, margin_in=0.75, extra=0.0):
    """extra: points of additional space after each bullet (twice that before roles and
    section headings), used to fill page 2 evenly."""
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
        _spacing(h, before=7 + 2 * extra, after=3, size=body_pt + 1)
        h.paragraph_format.keep_with_next = True
        _add_runs(h, title_text.upper(), body_pt + 1, color=color, bold=True)
        _bottom_border(h, hex_color)
        is_skills = title_text.lower() == "skills"
        in_roles = title_text.lower() in ("experience", "projects")
        expect_date, role_par = False, None
        for line in lines:
            if line.startswith("### "):
                role_par = doc.add_paragraph()
                _spacing(role_par, before=5 + 2 * extra, size=body_pt)
                role_par.paragraph_format.keep_with_next = True
                _add_runs(role_par, line[4:], body_pt, bold=True)
                expect_date = True
            elif expect_date and DATE_LINE.search(line) and len(line) < 60:
                # Dates right-aligned on the role line via a tab stop (no tables: ATS-safe),
                # bold in the company color so the timeline stands out.
                role_par.paragraph_format.tab_stops.add_tab_stop(content_width,
                                                                 WD_TAB_ALIGNMENT.RIGHT)
                _set_font(role_par.add_run("\t" + line), body_pt, bold=True, color=color)
                expect_date = False
            elif line.startswith("- "):
                text = line[2:]
                if is_skills and ":" in text:
                    p = doc.add_paragraph()
                    _spacing(p, after=1 + extra / 2, size=body_pt)
                    label, _, rest = text.partition(":")
                    _set_font(p.add_run(label.strip() + ": "), body_pt, bold=True)
                    _add_runs(p, rest.strip(), body_pt)
                else:
                    p = doc.add_paragraph(style="List Bullet")
                    _spacing(p, after=1 + extra, size=body_pt)
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
    for paragraph in doc.paragraphs:
        paragraph.paragraph_format.widow_control = False
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


def pdf_layout(pdf_path, margin_in):
    """-> (pages, fill of the last page 0..1): how far down the usable area the last text sits."""
    from pypdf import PdfReader
    reader = PdfReader(str(pdf_path))
    last = reader.pages[-1]
    height = float(last.mediabox.height)
    ys = []

    def visit(text, cm, tm, *_):
        if text.strip():
            ys.append(tm[5] * cm[3] + cm[5] if cm else tm[5])

    last.extract_text(visitor_text=visit)
    top, bottom = height - margin_in * 72, margin_in * 72
    fill = (top - min(ys)) / (top - bottom) if ys else 0.0
    return len(reader.pages), max(0.0, min(1.0, fill))


def measure(docx_path, margin_in):
    """-> (pages, last-page fill) as LibreOffice lays the document out, or (None, None)."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = to_pdf(docx_path, tmp)
        if not pdf:
            return None, None
        return pdf_layout(pdf, margin_in)


def count_pages(docx_path):
    """Pages as LibreOffice lays the document out (None if LibreOffice isn't installed)."""
    return measure(docx_path, 0.5)[0]


def _carlito():
    for path in CARLITO_CANDIDATES:
        if Path(path).exists():
            return path
    try:
        found = subprocess.run(["fc-match", "-f", "%{file}", "Carlito"], capture_output=True,
                               text=True).stdout.strip()
        return found if found and "arlito" in found else None
    except Exception:
        return None


def line_fill(md_text, body_pt, margin_in):
    """-> [(role heading, bullet text, lines, last-line fill 0..1)] for every experience bullet,
    wrapping words greedily at the bullet's text width, measured with Calibri's metrics."""
    from PIL import ImageFont
    path = _carlito()
    if not path:
        return []
    font = ImageFont.truetype(path, size=100)          # measure at 100 units, scale to pt
    scale = body_pt / 100.0
    width_pt = (8.5 - 2 * margin_in - BULLET_INDENT_IN) * 72

    def text_width(text):
        return font.getlength(text) * scale

    out, role = [], None
    _, _, sections = parse(clean_dashes(md_text))
    for title_text, lines in sections:
        if title_text.lower() not in ("experience", "projects"):
            continue
        for line in lines:
            if line.startswith("### "):
                role = line[4:]
            elif line.startswith("- "):
                text = re.sub(r"\*\*(.+?)\*\*", r"\1", line[2:])
                n, current = 1, ""
                for word in text.split():
                    trial = f"{current} {word}".strip()
                    if current and text_width(trial) > width_pt:
                        n, current = n + 1, word
                    else:
                        current = trial
                out.append((role, text, n, text_width(current) / width_pt))
    return out


def build_fitted(md_text, out_path, accent=None, title="Resume"):
    """Roomiest layout that fits MAX_PAGES with page 2 at most PAGE2_MAX full, then stretch
    spacing until page 2 is at least PAGE2_MIN full. -> (accent hex, pages, body pt).
    build_fitted.last_layout = (body pt, margin in, extra pt); .last_fill = page-2 fill."""
    pages = fill = hex_color = body_pt = margin = None
    for body_pt, margin in LAYOUTS:
        hex_color = build(md_text, out_path, accent, title, body_pt, margin)
        pages, fill = measure(out_path, margin)
        if pages is None:                       # no LibreOffice: cannot measure, keep roomiest
            break
        if pages < MAX_PAGES or (pages == MAX_PAGES and fill <= PAGE2_MAX):
            break
    extra = 0.0
    if pages == MAX_PAGES and fill is not None and fill < PAGE2_MIN:
        step = 0.5
        while extra + step <= MAX_EXTRA_PT:
            build(md_text, out_path, accent, title, body_pt, margin, extra + step)
            trial_pages, trial_fill = measure(out_path, margin)
            if trial_pages != MAX_PAGES or trial_fill > PAGE2_MAX:
                break                            # one step too far: keep the previous spacing
            extra, fill = extra + step, trial_fill
            if fill >= PAGE2_MIN:
                break
        build(md_text, out_path, accent, title, body_pt, margin, extra)
    build_fitted.last_layout = (body_pt, margin, extra)
    build_fitted.last_fill = fill
    return hex_color, pages, body_pt


build_fitted.last_layout, build_fitted.last_fill = None, None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("markdown")
    parser.add_argument("docx")
    parser.add_argument("--accent")
    parser.add_argument("--title", default="Resume")
    parser.add_argument("--pdf", action="store_true", help="also write the PDF next to the docx")
    parser.add_argument("--fill-report", action="store_true",
                        help="list bullets whose last line is under 70%% full")
    args = parser.parse_args()
    md = Path(args.markdown).read_text(encoding="utf-8")
    hex_color, pages, size = build_fitted(md, args.docx, args.accent, args.title)
    fill = build_fitted.last_fill
    print(f"Built {args.docx} ({pages if pages is not None else '?'} pages, {size}pt "
          f"{FONT}, accent {hex_color}, page {pages} {round(fill * 100) if fill is not None else '?'}% "
          f"full, extra spacing {build_fitted.last_layout[2]}pt)")
    if args.pdf:
        pdf = to_pdf(args.docx, Path(args.docx).parent)
        print(f"PDF: {pdf}")
    if args.fill_report:
        body_pt, margin, _ = build_fitted.last_layout
        weak = [(r, t, n, f) for r, t, n, f in line_fill(md, body_pt, margin) if f < 0.7]
        if not weak:
            print("Line fill: every bullet's last line is at least 70% full")
        for role, text, n, fill in weak:
            print(f"  short last line ({fill:.0%} of line {n}) | {role.split('|')[1].strip()} | "
                  f"{text[:70]}...")
