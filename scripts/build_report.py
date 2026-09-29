"""Builds TECHNICAL_REPORT.pdf from docs/TECHNICAL_REPORT.md.

The template's prose numbers are hand-written (verified against
reports/report_data_pack.md, which is itself generated straight from
reports/ -- see scripts/collect_report_facts.py). This script fills the
two visual placeholders ({{ARCH_SVG}}, {{CALLS_CHART}}) from
reports/report_data_pack.json so the chart at least always matches the
current model_calls distribution, converts the result to HTML (compact
print CSS) and prints it to PDF via headless Edge/Chrome, then checks the
page count with pypdf (fails if over 4 pages).

Usage:
    python scripts/build_report.py
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

TEMPLATE_PATH = ROOT / "docs" / "TECHNICAL_REPORT.md"
REPORTS_DIR = ROOT / "reports"
DATA_PACK_JSON = REPORTS_DIR / "report_data_pack.json"
OUT_PDF = ROOT / "TECHNICAL_REPORT.pdf"
MAX_PAGES = 4


class ReportBuildError(Exception):
    pass


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def build_arch_svg() -> str:
    """A compact horizontal pipeline diagram matching Section 1's description."""
    stages = [
        "customer\nmessage",
        "language detect\n+ lexicon retrieval",
        "LLM \u2194 tools\n(calculate_order /\nsave_lead / escalate)",
        "reply guards\n(amount, %, privacy,\ncanary, tool-leak,\nlanguage, length)",
        "safety nets\n(complaint, discount,\nlead-contact)",
        "response\n(disclosure + sources)",
    ]
    box_w, box_h, gap = 108, 58, 22
    total_w = len(stages) * box_w + (len(stages) - 1) * gap
    total_h = box_h + 16
    parts = [
        f'<svg viewBox="0 0 {total_w} {total_h}" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;height:auto;font-family:Arial,sans-serif;">'
    ]
    for i, stage in enumerate(stages):
        x = i * (box_w + gap)
        y = 4
        fill = "#f4ede2" if i in (2,) else "#eef2f7"
        stroke = "#7a1f2b" if i in (2,) else "#4a6785"
        parts.append(
            f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="6" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>'
        )
        lines = stage.split("\n")
        line_h = 11
        start_y = y + box_h / 2 - (len(lines) - 1) * line_h / 2 + 3
        for li, line in enumerate(lines):
            parts.append(
                f'<text x="{x + box_w / 2}" y="{start_y + li * line_h}" '
                f'text-anchor="middle" font-size="8.5" fill="#222">{line}</text>'
            )
        if i < len(stages) - 1:
            ax = x + box_w
            ay = y + box_h / 2
            parts.append(
                f'<line x1="{ax}" y1="{ay}" x2="{ax + gap - 4}" y2="{ay}" '
                f'stroke="#666" stroke-width="1.4" marker-end="url(#arrow)"/>'
            )
    parts.insert(
        1,
        '<defs><marker id="arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" '
        'orient="auto"><path d="M0,0 L6,3 L0,6 z" fill="#666"/></marker></defs>',
    )
    parts.append("</svg>")
    return (
        '<div style="margin:6pt 0;">' + "".join(parts) + "</div>"
    )


def build_calls_chart(dist_raw: dict[str, int], total: int) -> str:
    """A compact horizontal bar chart of the model_calls distribution."""
    order = ["1", "2", "3", "4"]
    max_count = max(dist_raw.get(k, 0) for k in order) or 1
    chart_w = 420
    bar_max_w = 260
    row_h = 20
    rows = []
    for i, k in enumerate(order):
        count = dist_raw.get(k, 0)
        pct = count / total * 100 if total else 0
        bar_w = bar_max_w * count / max_count
        y = i * row_h
        rows.append(
            f'<text x="0" y="{y + 13}" font-size="8.5" fill="#222">{k} call{"s" if k != "1" else ""}</text>'
            f'<rect x="42" y="{y + 2}" width="{bar_w:.1f}" height="14" rx="2" fill="#c76b1a"/>'
            f'<text x="{42 + bar_w + 6:.1f}" y="{y + 13}" font-size="8.5" fill="#222">'
            f'{count} ({pct:.1f}%)</text>'
        )
    svg_h = len(order) * row_h + 4
    svg = (
        f'<svg viewBox="0 0 {chart_w} {svg_h}" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;max-width:420px;height:auto;font-family:Arial,sans-serif;">'
        + "".join(rows)
        + "</svg>"
    )
    return f'<div style="margin:6pt 0;"><b style="font-size:9pt;">model_calls per customer message ({total} messages)</b>{svg}</div>'


def build_filled_markdown() -> str:
    template = _read(TEMPLATE_PATH)

    if not DATA_PACK_JSON.exists():
        raise ReportBuildError(
            f"{DATA_PACK_JSON} not found -- run scripts/collect_report_facts.py first."
        )
    data_pack = json.loads(_read(DATA_PACK_JSON))
    dive = data_pack["F_submission_deep_dive"]

    filled = template
    filled = filled.replace("{{ARCH_SVG}}", build_arch_svg())
    filled = filled.replace(
        "{{CALLS_CHART}}",
        build_calls_chart(dive["model_calls_distribution_raw"], dive["total_messages"]),
    )

    remaining = re.findall(r"\{\{[A-Z_]+\}\}", filled)
    if remaining:
        raise ReportBuildError(f"unfilled placeholders: {remaining}")

    return filled


_PRINT_CSS = """
@page { size: A4; margin: 10mm 13mm; }
body { font-family: "Segoe UI", Arial, sans-serif; font-size: 9.5pt; line-height: 1.32; color: #1a1a1a; }
h1 { font-size: 15pt; margin: 0 0 3pt; }
h2 { font-size: 11.5pt; margin: 10pt 0 4pt; border-bottom: 1px solid #ccc; padding-bottom: 2pt; }
h3 { font-size: 10pt; margin: 7pt 0 3pt; }
p { margin: 3.5pt 0; }
table { border-collapse: collapse; width: 100%; margin: 4pt 0 7pt; font-size: 8.2pt; }
th, td { border: 1px solid #999; padding: 1.5pt 4pt; text-align: left; }
th { background: #eee; }
pre { background: #f4f4f4; padding: 5pt; font-size: 7.8pt; overflow-x: auto; white-space: pre-wrap; }
code { font-size: 8.2pt; background: #f4f4f4; padding: 0 2pt; }
ul, ol { margin: 2pt 0; padding-left: 15pt; }
li { margin: 1pt 0; }

.titleband { background: linear-gradient(120deg, #7a1f2b 0%, #c76b1a 100%); color: #fff; padding: 8pt 12pt; border-radius: 6pt; margin-bottom: 6pt; }
.titleband h1 { color: #fff; margin: 0 0 2pt; }
.titleband p { color: #f3e6d8; margin: 0; font-size: 8.5pt; }

.kpis { display: flex; flex-wrap: wrap; gap: 5pt; margin-bottom: 8pt; }
.kpi { flex: 1 1 21%; background: #f7f3ee; border: 1px solid #e0d5c5; border-radius: 5pt; padding: 5pt 6pt; text-align: center; }
.kpi b { display: block; font-size: 11pt; color: #7a1f2b; }
.kpi span { display: block; font-size: 7pt; color: #555; margin-top: 1pt; }

.callout { background: #fdf6ec; border-left: 3pt solid #c76b1a; padding: 5pt 8pt; margin: 6pt 0; font-size: 8.8pt; }

.footer { margin-top: 8pt; padding-top: 5pt; border-top: 1px solid #ccc; font-size: 7.3pt; color: #444; }
"""


def _inline_md_to_html(text: str) -> str:
    """Table cells are inserted as literal text (not run through the
    `markdown` package), so **bold**/`code` inside a cell -- e.g. the
    **Overall** summary row -- needs its own tiny inline pass."""
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    return text


def _markdown_table_to_html(md_table: str) -> str:
    lines = [ln for ln in md_table.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return f"<pre>{md_table}</pre>"
    header_cells = [_inline_md_to_html(c.strip()) for c in lines[0].strip("|").split("|")]
    body_lines = lines[2:]
    html = ["<table>", "<thead><tr>"]
    html += [f"<th>{c}</th>" for c in header_cells]
    html.append("</tr></thead><tbody>")
    for line in body_lines:
        cells = [_inline_md_to_html(c.strip()) for c in line.strip("|").split("|")]
        html.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    html.append("</tbody></table>")
    return "\n".join(html)


def markdown_to_html(md_text: str) -> str:
    import markdown as markdown_pkg

    def _replace_table(match: re.Match) -> str:
        return "\n\n" + _markdown_table_to_html(match.group(0)) + "\n\n"

    md_with_html_tables = re.sub(r"(?:^\|.*\|\s*$\n?)+", _replace_table, md_text, flags=re.MULTILINE)
    body = markdown_pkg.markdown(md_with_html_tables, extensions=["fenced_code"])
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<style>{_PRINT_CSS}</style></head><body>{body}</body></html>"
    )


def _find_browser() -> str:
    names = ["msedge", "microsoft-edge", "google-chrome", "chromium", "chromium-browser", "chrome"]
    for name in names:
        found = shutil.which(name)
        if found:
            return found

    candidate_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/microsoft-edge",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
    ]
    for path in candidate_paths:
        if Path(path).exists():
            return path

    raise ReportBuildError(
        "Could not find a headless-capable browser (Edge or Chrome) on PATH or in common install "
        "locations. Install Microsoft Edge or Google Chrome, or add one to PATH, then retry."
    )


def html_to_pdf(html_path: Path, pdf_path: Path) -> None:
    browser = _find_browser()
    cmd = [
        browser,
        "--headless",
        "--disable-gpu",
        f"--print-to-pdf={pdf_path}",
        "--no-pdf-header-footer",
        "--print-to-pdf-no-header",
        str(html_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0 or not pdf_path.exists():
        raise ReportBuildError(
            f"headless PDF print failed (exit {result.returncode}): {result.stderr[:500]}"
        )


def check_page_count(pdf_path: Path) -> int:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    return len(reader.pages)


def main() -> int:
    try:
        filled_md = build_filled_markdown()
    except ReportBuildError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1

    html = markdown_to_html(filled_md)
    html_path = ROOT / "reports" / "_technical_report.html"
    html_path.write_text(html, encoding="utf-8")

    try:
        html_to_pdf(html_path, OUT_PDF)
    except ReportBuildError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1

    try:
        page_count = check_page_count(OUT_PDF)
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: could not read generated PDF: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {OUT_PDF} ({page_count} page{'s' if page_count != 1 else ''}).")
    if page_count > MAX_PAGES:
        print(f"FATAL: report is {page_count} pages, exceeds the {MAX_PAGES}-page limit.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
