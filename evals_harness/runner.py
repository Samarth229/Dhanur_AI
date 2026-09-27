"""Orchestrates an eval run: health check, warm-up, then runs x cases x turns
over HTTP, running checks and building the report."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evals_harness.checks import run_checks
from evals_harness.client import EvalClient
from evals_harness.loader import Case, CaseLoadError, load_cases
from evals_harness.metrics import aggregate_runs, compute_run_metrics
from evals_harness.report import write_reports


def _run_one_case(
    client: EvalClient, case: Case, conversation_id: str, data_dir: Path
) -> dict[str, Any]:
    turns_record: list[dict[str, Any]] = []
    turn_bodies: list[dict[str, Any]] = []
    turn_latencies: list[float] = []
    turn_tokens: list[tuple[int, int]] = []

    for turn_message in case.turns:
        result = client.post_chat(conversation_id, turn_message)
        turns_record.append(
            {
                "request": {"conversation_id": conversation_id, "message": turn_message},
                "response": result.body,
                "status_code": result.status_code,
                "latency_ms": result.latency_ms,
                "error": result.error,
            }
        )
        if not result.ok:
            return {
                "case_id": case.id,
                "category": case.category,
                "error": True,
                "error_reason": result.error or f"HTTP {result.status_code}",
                "passed": False,
                "checks": None,
                "turns": turns_record,
                "turn_latencies_ms": turn_latencies,
                "turn_tokens": turn_tokens,
            }

        turn_bodies.append(result.body)
        turn_latencies.append(result.latency_ms)
        usage = result.body.get("usage", {})
        turn_tokens.append((usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)))

    checks = run_checks(case, turn_bodies, data_dir)
    passed = all(c.passed for c in checks)

    return {
        "case_id": case.id,
        "category": case.category,
        "error": False,
        "error_reason": None,
        "passed": passed,
        "checks": checks,
        "turns": turns_record,
        "turn_latencies_ms": turn_latencies,
        "turn_tokens": turn_tokens,
    }


def run_eval(
    cases_path: str,
    settings,
    runs: int | None = None,
    base_url: str | None = None,
    label: str | None = None,
    transport=None,
) -> int:
    runs = runs or settings.eval.runs
    base_url = base_url or settings.eval.base_url
    timeout_s = settings.eval.request_timeout_s
    data_dir = settings.paths.data_dir

    try:
        cases = load_cases(cases_path)
    except CaseLoadError as exc:
        print(f"Error loading cases: {exc}")
        return 1

    client = EvalClient(base_url, timeout_s, transport=transport)

    health = client.get_health()
    if not health.ok:
        print(f"Service not reachable at {base_url}. Start it with: python manage.py run")
        client.close()
        return 1
    model = (health.body or {}).get("model", "unknown")

    # Warm-up: one POST /chat excluded from all metrics.
    client.post_chat("eval-warmup", "Hello")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    all_run_results: list[list[dict[str, Any]]] = []
    total = len(cases)

    for run_index in range(1, runs + 1):
        run_results: list[dict[str, Any]] = []
        for i, case in enumerate(cases, start=1):
            conversation_id = f"eval-{stamp}-{case.id}-r{run_index}"
            case_result = _run_one_case(client, case, conversation_id, data_dir)
            run_results.append(case_result)

            total_latency_s = sum(case_result["turn_latencies_ms"]) / 1000
            if case_result["error"]:
                print(f"[run {run_index}/{runs}] {i}/{total} {case.id} ERROR ({case_result['error_reason']})")
            elif case_result["passed"]:
                print(f"[run {run_index}/{runs}] {i}/{total} {case.id} PASS ({total_latency_s:.1f}s)")
            else:
                failed_names = [c.name for c in case_result["checks"] if not c.passed]
                print(
                    f"[run {run_index}/{runs}] {i}/{total} {case.id} FAIL "
                    f"({total_latency_s:.1f}s) failed: {', '.join(failed_names)}"
                )
        all_run_results.append(run_results)

    client.close()

    run_metrics_list = [compute_run_metrics(run_results, settings) for run_results in all_run_results]
    aggregated = aggregate_runs(run_metrics_list, all_run_results)

    meta = {
        "date": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "base_url": base_url,
        "cases_file": str(cases_path),
        "case_count": len(cases),
        "runs": runs,
        "label": label,
        "config": {
            "history_messages": settings.agent.history_messages,
            "max_sources": settings.agent.max_sources,
            "allowed_percentages": list(settings.agent.allowed_percentages),
            "max_model_calls": settings.llm.max_model_calls,
            "reply_max_chars": settings.reply.max_chars,
        },
    }

    write_reports(settings.paths.reports_dir, meta, all_run_results, aggregated)

    print()
    print(f"Pass rate (mean of {runs} runs): {aggregated.mean.pass_rate * 100:.1f}%")
    print(f"Report: {settings.paths.reports_dir / 'eval_report.json'}")
    print(f"Summary: {settings.paths.reports_dir / 'summary.md'}")
    return 0
