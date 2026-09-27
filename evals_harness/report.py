"""Writes reports/eval_report.json and reports/summary.md, plus a timestamped
copy of both under reports/runs/<stamp>[-label]/."""
from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evals_harness.metrics import AggregatedMetrics, RunMetrics


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def build_report_json(
    meta: dict[str, Any],
    runs: list[list[dict[str, Any]]],
) -> dict[str, Any]:
    """runs[run_index][case_index] = {case_id, category, turns: [...], checks: [...], error, passed}"""

    def serialize_check(c) -> dict[str, Any]:
        return {"name": c.name, "passed": c.passed, "details": c.details}

    def serialize_case_run(r: dict[str, Any]) -> dict[str, Any]:
        return {
            "case_id": r["case_id"],
            "category": r["category"],
            "error": r["error"],
            "error_reason": r.get("error_reason"),
            "passed": r["passed"],
            "turns": r["turns"],
            "checks": [serialize_check(c) for c in r["checks"]] if r["checks"] else [],
        }

    return {
        "meta": meta,
        "runs": [[serialize_case_run(r) for r in run] for run in runs],
    }


def _metrics_table_row(label: str, mean: RunMetrics, worst: RunMetrics) -> str:
    def row(name, m_val, w_val):
        return f"| {name} | {m_val} | {w_val} |"

    return "\n".join(
        [
            row("Pass rate", _pct(mean.pass_rate), _pct(worst.pass_rate)),
            row("Invented-amount rate", _pct(mean.invented_amount_rate), _pct(worst.invented_amount_rate)),
            row("Action accuracy", _pct(mean.action_accuracy), _pct(worst.action_accuracy)),
            row("AI-disclosure rate", _pct(mean.ai_disclosure_rate), _pct(worst.ai_disclosure_rate)),
            row("Latency p50 (ms)", f"{mean.latency_p50:.0f}", f"{worst.latency_p50:.0f}"),
            row("Latency p95 (ms)", f"{mean.latency_p95:.0f}", f"{worst.latency_p95:.0f}"),
            row("Avg tokens in", f"{mean.avg_tokens_in:.0f}", f"{worst.avg_tokens_in:.0f}"),
            row("Avg tokens out", f"{mean.avg_tokens_out:.0f}", f"{worst.avg_tokens_out:.0f}"),
            row("Cost (INR / 100 conversations)", f"{mean.cost_inr_per_100_conversations:.2f}", f"{worst.cost_inr_per_100_conversations:.2f}"),
            row("Errored case-runs", f"{mean.error_count:.1f}", f"{worst.error_count}"),
        ]
    )


def build_summary_md(
    meta: dict[str, Any],
    aggregated: AggregatedMetrics,
    runs: list[list[dict[str, Any]]],
) -> str:
    lines: list[str] = []
    lines.append("# Evaluation summary")
    lines.append("")
    lines.append(f"Date: {meta['date']}")
    lines.append(f"Model: {meta['model']}")
    lines.append(f"Cases file: {meta['cases_file']}")
    lines.append(f"Cases: {meta['case_count']}  Runs: {meta['runs']}")
    if meta.get("label"):
        lines.append(f"Label: {meta['label']}")
    lines.append("")

    lines.append("## Metrics")
    lines.append("")
    lines.append("| Metric | Mean of runs | Worst run |")
    lines.append("|---|---|---|")
    lines.append(_metrics_table_row("", aggregated.mean, aggregated.worst))
    lines.append("")

    lines.append("## By category (mean pass rate across runs)")
    lines.append("")
    lines.append("| Category | Mean pass rate | Worst run pass rate |")
    lines.append("|---|---|---|")
    for cat in sorted(aggregated.mean.category_pass_rate):
        lines.append(
            f"| {cat} | {_pct(aggregated.mean.category_pass_rate[cat])} | "
            f"{_pct(aggregated.worst.category_pass_rate.get(cat, 0.0))} |"
        )
    lines.append("")

    lines.append("## Failing cases")
    lines.append("")
    total_runs = len(runs)
    case_ids_in_order = [r["case_id"] for r in runs[0]] if runs else []
    any_failing = False
    for case_id in case_ids_in_order:
        run_results = [next(r for r in run if r["case_id"] == case_id) for run in runs]
        pass_count = sum(1 for r in run_results if r["passed"])
        if pass_count == total_runs:
            continue
        any_failing = True
        failed_run = next(r for r in run_results if not r["passed"])
        failed_checks = (
            ["error: " + str(failed_run.get("error_reason"))]
            if failed_run["error"]
            else [c.name for c in failed_run["checks"] if not c.passed]
        )
        reply_snippet = ""
        if failed_run["turns"]:
            last_turn = failed_run["turns"][-1]
            reply_snippet = (last_turn.get("response") or {}).get("reply", "")[:150]
        lines.append(f"- **{case_id}** ({pass_count}/{total_runs} passed) -- failed: {', '.join(failed_checks)}")
        if reply_snippet:
            lines.append(f"  Reply excerpt: {reply_snippet!r}")
    if not any_failing:
        lines.append("None -- every case passed in every run.")
    lines.append("")

    lines.append("## Flaky cases")
    lines.append("")
    if aggregated.flaky_cases:
        for case_id, ratio in aggregated.flaky_cases.items():
            lines.append(f"- {case_id}: {ratio}")
    else:
        lines.append("None.")
    lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append(
        "p50 and p95 latency use the nearest-rank method: sort the samples and take the "
        "value at rank ceil(p/100 * n) (1-indexed). Invented-amount rate, action accuracy and "
        "AI-disclosure rate are computed only over case-runs that completed without an HTTP "
        "error (errored case-runs are still counted as failures for the overall pass rate, and "
        "reported separately as 'errored case-runs')."
    )
    lines.append("")

    return "\n".join(lines)


def write_reports(
    reports_dir: Path,
    meta: dict[str, Any],
    runs: list[list[dict[str, Any]]],
    aggregated: AggregatedMetrics,
) -> tuple[Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)

    report_json = build_report_json(meta, runs)
    summary_md = build_summary_md(meta, aggregated, runs)

    json_path = reports_dir / "eval_report.json"
    summary_path = reports_dir / "summary.md"
    json_path.write_text(json.dumps(report_json, indent=2, ensure_ascii=False), encoding="utf-8")
    summary_path.write_text(summary_md, encoding="utf-8")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    label = meta.get("label")
    run_dir_name = f"{stamp}-{label}" if label else stamp
    run_dir = reports_dir / "runs" / run_dir_name
    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(json_path, run_dir / "eval_report.json")
    shutil.copy2(summary_path, run_dir / "summary.md")

    return json_path, summary_path
