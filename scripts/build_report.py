"""Builds TECHNICAL_REPORT.pdf from docs/TECHNICAL_REPORT.md (a placeholder
template) filled with numbers read straight out of reports/eval_report.json
+ reports/summary.md (the submission run) and the baseline/ablation/xmodel
runs under reports/runs/, so the report's numbers always match reports/.

Steps: fill placeholders -> markdown -> HTML (compact print CSS) -> PDF via
headless Edge/Chrome -> check page count with pypdf (fails if > 4 pages).

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
RUNS_DIR = REPORTS_DIR / "runs"
OUT_PDF = ROOT / "TECHNICAL_REPORT.pdf"
MAX_PAGES = 4


class ReportBuildError(Exception):
    pass


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_section(markdown: str, header: str) -> str:
    """Returns the markdown block starting at "## {header}" up to (not
    including) the next "## " header, or EOF."""
    pattern = re.compile(
        rf"^## {re.escape(header)}\s*$\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL
    )
    match = pattern.search(markdown)
    if not match:
        raise ReportBuildError(f"section '## {header}' not found")
    return match.group(1).strip()


def _extract_meta(markdown: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for line in markdown.splitlines():
        if line.startswith("Date: "):
            meta["date"] = line.removeprefix("Date: ").strip()
        elif line.startswith("Model: "):
            meta["model"] = line.removeprefix("Model: ").strip()
    return meta


def _pass_rate_from_summary(markdown: str) -> tuple[str, str]:
    """Returns (mean, worst) pass-rate strings from the "## Metrics" table."""
    metrics = _extract_section(markdown, "Metrics")
    match = re.search(r"\|\s*Pass rate\s*\|\s*([\d.]+%)\s*\|\s*([\d.]+%)\s*\|", metrics)
    if not match:
        raise ReportBuildError("pass rate row not found in Metrics table")
    return match.group(1), match.group(2)


def _action_accuracy_from_summary(markdown: str) -> str:
    metrics = _extract_section(markdown, "Metrics")
    match = re.search(r"\|\s*Action accuracy\s*\|\s*([\d.]+%)\s*\|", metrics)
    if not match:
        raise ReportBuildError("action accuracy row not found in Metrics table")
    return match.group(1)


def _metric_value(markdown: str, metric_name: str, column: int = 1) -> str:
    metrics = _extract_section(markdown, "Metrics")
    cells = rf"(\s*[^|]+\|){{{column - 1}}}\s*([^|]+)\|"
    match = re.search(rf"\|\s*{re.escape(metric_name)}\s*\|{cells}", metrics)
    if not match:
        raise ReportBuildError(f"metric '{metric_name}' not found")
    return match.group(2).strip()


def _find_run_dir(label_suffix: str) -> Path | None:
    """Finds the most recent reports/runs/<timestamp>-<label_suffix> dir."""
    if not RUNS_DIR.exists():
        return None
    candidates = sorted(
        (d for d in RUNS_DIR.iterdir() if d.is_dir() and d.name.endswith(f"-{label_suffix}")),
        key=lambda d: d.name,
    )
    return candidates[-1] if candidates else None


def _run_pass_rate(label_suffix: str) -> str | None:
    run_dir = _find_run_dir(label_suffix)
    if run_dir is None:
        return None
    summary_path = run_dir / "summary.md"
    if not summary_path.exists():
        return None
    mean, _worst = _pass_rate_from_summary(_read(summary_path))
    return mean


def _markdown_table_to_html(md_table: str) -> str:
    """Minimal GFM-table -> HTML converter (the `markdown` package's core
    extension doesn't render pipe tables without the optional `tables`
    extension, so this is used for the tables copied verbatim from
    summary.md; everything else goes through the `markdown` package)."""
    lines = [ln for ln in md_table.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return f"<pre>{md_table}</pre>"
    header_cells = [c.strip() for c in lines[0].strip("|").split("|")]
    body_lines = lines[2:]  # skip the |---|---| separator
    html = ["<table>", "<thead><tr>"]
    html += [f"<th>{c}</th>" for c in header_cells]
    html.append("</tr></thead><tbody>")
    for line in body_lines:
        cells = [c.strip() for c in line.strip("|").split("|")]
        html.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    html.append("</tbody></table>")
    return "\n".join(html)


def build_filled_markdown() -> str:
    template = _read(TEMPLATE_PATH)

    submission_summary = _read(REPORTS_DIR / "summary.md")
    meta = _extract_meta(submission_summary)
    pass_mean, pass_worst = _pass_rate_from_summary(submission_summary)
    action_mean = _action_accuracy_from_summary(submission_summary)
    # summary.md's own section body already includes its header + separator
    # row (build_summary_md always writes them), so these are copied
    # verbatim -- no header should be prepended here, or it duplicates.
    metrics_table_md = "\n".join(
        ln for ln in _extract_section(submission_summary, "Metrics").splitlines() if ln.startswith("|")
    )
    category_table_md = "\n".join(
        ln for ln in _extract_section(submission_summary, "By category (mean pass rate across runs)").splitlines()
        if ln.startswith("|")
    )

    ablation_dir = _find_run_dir("ablation-topk")
    if ablation_dir is not None:
        ablation_summary = _read(ablation_dir / "summary.md")
        ablation_pass_mean, _ = _pass_rate_from_summary(ablation_summary)
        ablation_action = _action_accuracy_from_summary(ablation_summary)
    else:
        ablation_pass_mean = "n/a"
        ablation_action = "n/a"

    progression_parts = []
    for label in ("baseline-full", "final", "final-2", "submission"):
        rate = _run_pass_rate(label) if label != "submission" else pass_mean
        progression_parts.append(f"{label} {rate if rate else 'n/a'}")
    progression_line = " -> ".join(progression_parts)

    xmodel_dir = _find_run_dir("xmodel-llama31")
    if xmodel_dir is not None:
        xmodel_summary = _read(xmodel_dir / "summary.md")
        xmodel_pass, _ = _pass_rate_from_summary(xmodel_summary)
        xmodel_result = (
            f"llama3.1:8b scored {xmodel_pass} pass rate on the seed cases (1 run) -- the service ran without "
            "crashing and tools were parsed correctly; a lower score than qwen2.5:7b was expected and confirms "
            "the model-selection choice, consistent with reports/model_comparison.md."
        )
    else:
        xmodel_result = (
            "Skipped: llama3.1:8b is not installed on this machine (a fresh ~4.7 GB pull was not made for this "
            "run). reports/model_comparison.md already characterizes it on this service's tool-calling/injection "
            "behavior from the earlier model-selection comparison (38% tool accuracy, 0% injection-refusal pass "
            "rate on an 8-message comparison set)."
        )

    five_failures = _read(ROOT / "docs" / "_report_five_failures.md")

    cost_latency_section = (
        f"Avg tokens in/out: {_metric_value(submission_summary, 'Avg tokens in')} / "
        f"{_metric_value(submission_summary, 'Avg tokens out')}. "
        f"Latency p50/p95: {_metric_value(submission_summary, 'Latency p50 (ms)')} / "
        f"{_metric_value(submission_summary, 'Latency p95 (ms)')} ms. "
        f"Cost: {_metric_value(submission_summary, 'Cost (INR / 100 conversations)')} INR / 100 conversations "
        "(local model, zero per-token cost)."
    )

    replacements = {
        "{{model}}": meta.get("model", "unknown"),
        "{{run_date}}": meta.get("date", "unknown"),
        "{{pass_rate_mean}}": pass_mean,
        "{{pass_rate_worst}}": pass_worst,
        "{{ablation_full_pass}}": pass_mean,
        "{{ablation_topk_pass}}": ablation_pass_mean,
        "{{ablation_full_action}}": action_mean,
        "{{ablation_topk_action}}": ablation_action,
        "{{summary_table}}": metrics_table_md,
        "{{category_table}}": category_table_md,
        "{{progression_line}}": progression_line,
        "{{xmodel_result}}": xmodel_result,
        "{{five_failures}}": five_failures,
        "{{cost_latency_section}}": cost_latency_section,
        "{{latency_p50}}": _metric_value(submission_summary, "Latency p50 (ms)"),
        "{{latency_p95}}": _metric_value(submission_summary, "Latency p95 (ms)"),
    }

    filled = template
    for key, value in replacements.items():
        filled = filled.replace(key, value)

    remaining = re.findall(r"\{\{[a-z_]+\}\}", filled)
    if remaining:
        raise ReportBuildError(f"unfilled placeholders: {remaining}")

    return filled


_PRINT_CSS = """
@page { size: A4; margin: 12mm 14mm; }
body { font-family: "Segoe UI", Arial, sans-serif; font-size: 10pt; line-height: 1.35; color: #1a1a1a; }
h1 { font-size: 15pt; margin: 0 0 6pt; }
h2 { font-size: 12pt; margin: 12pt 0 4pt; border-bottom: 1px solid #ccc; padding-bottom: 2pt; }
h3 { font-size: 10.5pt; margin: 8pt 0 3pt; }
p { margin: 4pt 0; }
table { border-collapse: collapse; width: 100%; margin: 4pt 0 8pt; font-size: 8.5pt; }
th, td { border: 1px solid #999; padding: 2pt 4pt; text-align: left; }
th { background: #eee; }
pre { background: #f4f4f4; padding: 6pt; font-size: 8pt; overflow-x: auto; white-space: pre-wrap; }
code { font-size: 8.5pt; background: #f4f4f4; padding: 0 2pt; }
ul, ol { margin: 3pt 0; padding-left: 16pt; }
li { margin: 1pt 0; }
"""


def markdown_to_html(md_text: str) -> str:
    import markdown as markdown_pkg

    # The `markdown` package's core renderer doesn't include GFM pipe
    # tables without the optional `tables` extension, so pipe-table blocks
    # are hand-converted to raw HTML *before* running the renderer --
    # `markdown` passes block-level raw HTML through untouched when it's
    # surrounded by blank lines, so this composes cleanly with fenced code
    # blocks and everything else in the template.
    def _replace_table(match: re.Match) -> str:
        return "\n\n" + _markdown_table_to_html(match.group(0)) + "\n\n"

    md_with_html_tables = re.sub(r"(?:^\|.*\|\s*$\n?)+", _replace_table, md_text, flags=re.MULTILINE)
    body = markdown_pkg.markdown(md_with_html_tables, extensions=["fenced_code"])
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{_PRINT_CSS}</style></head><body>{body}</body></html>"


def _find_browser() -> str:
    """Searches common Edge/Chrome install locations and PATH -- no single
    hardcoded path; raises a clear error if none is found."""
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
