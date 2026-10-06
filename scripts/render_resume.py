"""Render a tailored resume (markdown) into the branded "Classic accent" PDF (PRD v2 4.6).

    python scripts/render_resume.py <resume.md> <out.pdf> [--logo URL | --accent #RRGGBB] [--title TEXT]

markdown -> HTML (templates/resume_classic.html) -> PDF via headless Chromium. The same engine
runs locally (Chrome/Edge) and on Modal (Debian `chromium`), so both tailoring paths produce
identical output. Replaces the v1 Google-Docs build step.

Accent color = the company's logo color (dominant saturated color, darkened until it reads well
as text on white); falls back to navy when there's no logo or it's monochrome.
"""
import argparse
import colorsys
import html
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

import requests

from text_rules import clean_dashes

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "templates" / "resume_classic.html"
FONT_DIR = ROOT / "templates" / "fonts"
DEFAULT_ACCENT = "#1F3A5F"
MIN_CONTRAST = 4.5  # WCAG AA for normal text on white

BROWSER_CANDIDATES = [
    "chromium", "chromium-browser", "google-chrome", "chrome", "msedge",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


# ---------- accent color ----------

def _luminance(rgb):
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_on_white(rgb):
    return 1.05 / (_luminance(rgb) + 0.05)


def _readable(rgb):
    """Darken (keeping hue) until the color passes MIN_CONTRAST against white."""
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    while _contrast_on_white(rgb) < MIN_CONTRAST and l > 0.05:
        l -= 0.04
        rgb = tuple(round(c * 255) for c in colorsys.hls_to_rgb(h, l, s))
    return rgb


def accent_from_logo(logo_url):
    if not logo_url:
        return DEFAULT_ACCENT
    try:
        from PIL import Image
        resp = requests.get(logo_url, timeout=20)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGBA").resize((64, 64))
        buckets = Counter()
        for r, g, b, a in img.getdata():
            if a < 128:
                continue
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if s < 0.25 or v < 0.15 or v > 0.97:  # skip white, black, greys
                continue
            buckets[(r // 24 * 24 + 12, g // 24 * 24 + 12, b // 24 * 24 + 12)] += 1
        if not buckets or sum(buckets.values()) < 40:  # monochrome logo
            return DEFAULT_ACCENT
        rgb = _readable(buckets.most_common(1)[0][0])
        return "#{:02X}{:02X}{:02X}".format(*rgb)
    except Exception as e:
        print(f"  logo color fallback ({e})")
        return DEFAULT_ACCENT


# ---------- markdown -> html ----------

DATE_LINE = re.compile(r"\b(19|20)\d{2}\b|\bPresent\b", re.IGNORECASE)


def _inline(text):
    out = html.escape(text.strip())
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)


def _entry_html(heading, lines):
    dates, meta, bullets = "", [], []
    for line in lines:
        if line.startswith("- "):
            bullets.append(line[2:])
        elif not dates and not meta and DATE_LINE.search(line) and len(line) < 60:
            dates = line
        else:
            meta.append(line)
    parts = ['<div class="entry">',
             f'<div class="entry-head"><span class="entry-title">{_inline(heading)}</span>'
             f'<span class="entry-dates">{_inline(dates)}</span></div>']
    parts += [f'<p class="entry-meta">{_inline(m)}</p>' for m in meta]
    if bullets:
        parts.append("<ul>" + "".join(f"<li>{_inline(b)}</li>" for b in bullets) + "</ul>")
    parts.append("</div>")
    return "".join(parts)


def _section_html(title, lines):
    out = [f"<h2>{_inline(title)}</h2>"]
    if title.lower() == "skills":
        items = []
        for line in lines:
            if not line.startswith("- "):
                continue
            label, sep, rest = line[2:].partition(":")
            items.append(f"<li><b>{_inline(label)}:</b> {_inline(rest)}</li>" if sep
                         else f"<li>{_inline(line[2:])}</li>")
        out.append('<ul class="skills">' + "".join(items) + "</ul>")
        return "".join(out)

    heading, buf, loose = None, [], []

    def flush():
        if heading is not None:
            out.append(_entry_html(heading, buf))

    for line in lines:
        if line.startswith("### "):
            flush()
            heading, buf = line[4:], []
        elif heading is not None:
            buf.append(line)
        else:
            loose.append(line)
    bullets = [l[2:] for l in loose if l.startswith("- ")]
    paragraphs = [l for l in loose if not l.startswith("- ")]
    out += [f"<p>{_inline(p)}</p>" for p in paragraphs]
    if bullets:
        out.append("<ul>" + "".join(f"<li>{_inline(b)}</li>" for b in bullets) + "</ul>")
    flush()
    return "".join(out)


def markdown_to_body(md):
    lines = [l.rstrip() for l in md.splitlines()]
    name, header_lines, sections, current = "", [], [], None
    for line in lines:
        if not line.strip():
            continue
        if line.startswith("# ") and not name:
            name = line[2:].strip()
        elif line.startswith("## "):
            current = (line[3:].strip(), [])
            sections.append(current)
        elif current is None:
            header_lines.append(line.strip())
        else:
            current[1].append(line.strip())

    headline = header_lines[0] if header_lines else ""
    contact = " ".join(header_lines[1:])
    body = ["<header>", f"<h1>{_inline(name)}</h1>"]
    if headline:
        body.append(f'<p class="headline">{_inline(headline)}</p>')
    if contact:
        body.append(f'<p class="contact">{_inline(contact)}</p>')
    body.append("</header>")
    body += [_section_html(title, sec_lines) for title, sec_lines in sections]
    return "\n".join(body)


# ---------- pdf ----------

def find_browser():
    explicit = os.environ.get("CHROME_PATH")
    if explicit:
        return explicit
    for candidate in BROWSER_CANDIDATES:
        found = shutil.which(candidate) or (candidate if Path(candidate).exists() else None)
        if found:
            return found
    raise RuntimeError("No Chromium-based browser found (set CHROME_PATH)")


MAX_PAGES = 2
DENSITIES = ["", "compact", "tight"]
PAGE_OBJ = re.compile(rb"/Type\s*/Page(?![s\w])")


def _print_pdf(page_html, pdf_path):
    if pdf_path.exists():
        pdf_path.unlink()
    with tempfile.TemporaryDirectory() as tmp:
        html_path = Path(tmp) / "resume.html"
        html_path.write_text(page_html, encoding="utf-8")
        # Own profile dir per render: concurrent Chromium instances sharing the default profile
        # lock each other out (resumes are rendered in parallel).
        cmd = [find_browser(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
               f"--user-data-dir={Path(tmp) / 'profile'}",
               "--allow-file-access-from-files", f"--print-to-pdf={pdf_path}", html_path.as_uri()]
        if sys.platform.startswith("linux"):
            cmd.insert(1, "--no-sandbox")  # Modal runs as root; Chromium refuses the sandbox there
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise RuntimeError(f"PDF render failed: {result.stderr[-500:]}")
    return len(PAGE_OBJ.findall(pdf_path.read_bytes()))


HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def render(md_text, pdf_path, logo_url=None, title="Resume", accent=None):
    """Returns (accent, pages). Steps down density until the resume fits MAX_PAGES.

    `accent` (e.g. "#E1251B", the company's brand color) overrides the logo lookup -- used when
    the logo can't be downloaded (Claude's cloud sessions can't reach LinkedIn's image CDN). It is
    darkened the same way until it reads well as text on white."""
    md_text, title = clean_dashes(md_text), clean_dashes(title)
    if accent and HEX_COLOR.match(accent):
        rgb = tuple(int(accent[i:i + 2], 16) for i in (1, 3, 5))
        accent = "#{:02X}{:02X}{:02X}".format(*_readable(rgb))
    else:
        accent = accent_from_logo(logo_url)
    base = (TEMPLATE.read_text(encoding="utf-8")
            .replace("__TITLE__", html.escape(title))
            .replace("__FONT_DIR__", FONT_DIR.resolve().as_uri())
            .replace("__ACCENT__", accent)
            .replace("__BODY__", markdown_to_body(md_text)))

    pdf_path = Path(pdf_path).resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    for density in DENSITIES:
        pages = _print_pdf(base.replace("__DENSITY__", density), pdf_path)
        if pages <= MAX_PAGES:
            break
    return accent, pages


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("markdown")
    parser.add_argument("pdf")
    parser.add_argument("--logo")
    parser.add_argument("--title", default="Resume")
    parser.add_argument("--accent", help="brand color as #RRGGBB; overrides --logo")
    args = parser.parse_args()
    accent, pages = render(Path(args.markdown).read_text(encoding="utf-8"), args.pdf, args.logo,
                           args.title, args.accent)
    print(f"Rendered {args.pdf} ({pages} pages, accent {accent})")
