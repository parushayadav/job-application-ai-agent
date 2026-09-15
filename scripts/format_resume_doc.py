"""Populate a Google Doc with a tailored resume, converting markdown structure into
real Google Docs formatting (bold headers, bullet lists) instead of literal markdown
syntax. ATS-friendly: plain single-column text, bold section headers, real bullets,
no #, ##, ### or leading "- " characters left in the visible text.

Usage: format_resume_doc.py <markdown_path> <document_id>
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def _resolve_gws_command():
    gws_path = shutil.which("gws")
    if gws_path and gws_path.lower().endswith(".cmd"):
        # npm's Windows shim is a .cmd batch file, which Windows can only launch via a
        # nested cmd.exe -- and cmd.exe caps command lines at ~8191 chars, too small for a
        # full resume's batchUpdate JSON. Call the CLI's real JS entrypoint through
        # node.exe directly instead, which uses Windows' actual ~32K CreateProcess limit.
        run_js = Path(gws_path).parent / "node_modules" / "@googleworkspace" / "cli" / "run.js"
        if run_js.exists():
            return [shutil.which("node") or "node", str(run_js)]
    return [gws_path or "gws"]


GWS_CMD = _resolve_gws_command()


def gws(*args):
    result = subprocess.run([*GWS_CMD, *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gws {' '.join(args)} failed: {result.stderr}")
    return json.loads(result.stdout) if result.stdout.strip() else {}


DATE_RE = re.compile(r"\b(19|20)\d{2}\b")


def pt(n):
    return {"magnitude": n, "unit": "PT"}


def classify(line, prev_type):
    if line.startswith("# "):
        return "NAME", line[2:].strip()
    if line.startswith("## "):
        return "SECTION", line[3:].strip().upper()
    if line.startswith("### "):
        return "JOB_TITLE", line[4:].strip()
    if line.startswith("- "):
        return "BULLET", line[2:].strip()
    if prev_type == "NAME":
        return "ROLE", line.strip()
    if prev_type == "JOB_TITLE" and DATE_RE.search(line):
        return "DATE", line.strip()
    return "PLAIN", line.strip()


def parse(markdown_text):
    """Returns list of (type, text) blocks, blank lines dropped."""
    blocks = []
    prev_type = None
    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        block_type, text = classify(line, prev_type)
        blocks.append((block_type, text))
        prev_type = block_type
    return blocks


def build_requests(blocks):
    """Assembles full plain text + style/bullet requests using tracked char offsets."""
    text_parts = []
    style_spans = []  # (start, end, style_dict)
    bullet_ranges = []  # (start, end) contiguous bullet runs
    offset = 0
    current_bullet_start = None

    def append(s, block_type=None):
        nonlocal offset
        start = offset
        text_parts.append(s)
        offset += len(s)
        return start, offset

    prev_type = None
    for block_type, text in blocks:
        if block_type != "BULLET" and current_bullet_start is not None:
            bullet_ranges.append((current_bullet_start, offset))
            current_bullet_start = None

        if block_type == "NAME":
            start, end = append(text + "\n")
            style_spans.append((start, end - 1, {"bold": True, "fontSize": pt(16)}))
        elif block_type == "ROLE":
            start, end = append(text + "\n\n")
        elif block_type == "SECTION":
            prefix = "\n" if offset > 0 else ""
            start, end = append(prefix + text + "\n")
            start += len(prefix)
            style_spans.append((start, end - 1, {"bold": True, "fontSize": pt(12)}))
        elif block_type == "JOB_TITLE":
            prefix = "\n" if prev_type == "BULLET" else ""
            start, end = append(prefix + text + "\n")
            start += len(prefix)
            style_spans.append((start, end - 1, {"bold": True, "fontSize": pt(11)}))
        elif block_type == "DATE":
            start, end = append(text + "\n")
            style_spans.append((start, end - 1, {"italic": True}))
        elif block_type == "BULLET":
            start, end = append(text + "\n")
            if current_bullet_start is None:
                current_bullet_start = start
        else:  # PLAIN
            start, end = append(text + "\n\n")

        prev_type = block_type

    if current_bullet_start is not None:
        bullet_ranges.append((current_bullet_start, offset))

    full_text = "".join(text_parts)

    requests = [{"insertText": {"location": {"index": 1}, "text": full_text}}]

    for start, end, style in style_spans:
        text_style = {k: v for k, v in style.items()}
        fields = ",".join(text_style.keys())
        requests.append({
            "updateTextStyle": {
                "range": {"startIndex": start + 1, "endIndex": end + 1},
                "textStyle": text_style,
                "fields": fields,
            }
        })

    for start, end in bullet_ranges:
        requests.append({
            "createParagraphBullets": {
                "range": {"startIndex": start + 1, "endIndex": end + 1},
                "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
            }
        })

    return requests


if __name__ == "__main__":
    markdown_path, document_id = sys.argv[1], sys.argv[2]
    markdown_text = open(markdown_path).read()
    blocks = parse(markdown_text)
    requests = build_requests(blocks)
    gws("docs", "documents", "batchUpdate", "--params",
        json.dumps({"documentId": document_id}),
        "--json", json.dumps({"requests": requests}))
    print(f"Formatted {document_id} from {markdown_path}")
