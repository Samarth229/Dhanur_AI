"""Aggregates per-run and cross-run metrics from case-run results.

p50/p95 use the nearest-rank method: sort the samples, take the value at
index ceil(p/100 * n) - 1 (1-indexed rank). Documented again in the
generated summary.md.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


def nearest_rank_percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile / 100 * len(ordered)))
    return ordered[rank - 1]


@dataclass
class RunMetrics:
    pass_rate: float
    category_pass_rate: dict[str, float]
    invented_amount_rate: float
    error_count: int
    action_accuracy: float
    ai_disclosure_rate: float
    latency_p50: float
    latency_p95: float
    avg_tokens_in: float
    avg_tokens_out: float
    cost_inr_per_100_conversations: float


def compute_run_metrics(case_run_results: list[dict[str, Any]], settings) -> RunMetrics:
    """case_run_results: one dict per case-run for a single run, each with:
    'category', 'error' (bool), 'passed' (bool), 'checks' (list[CheckResult]
    or None if errored), 'turn_latencies_ms' (list), 'turn_tokens' (list of
    (prompt_tokens, completion_tokens))."""
    total = len(case_run_results)
    passed_count = sum(1 for r in case_run_results if r["passed"])
    pass_rate = passed_count / total if total else 0.0

    by_category: dict[str, list[bool]] = {}
    for r in case_run_results:
        by_category.setdefault(r["category"], []).append(r["passed"])
    category_pass_rate = {cat: sum(v) / len(v) for cat, v in by_category.items()}

    non_error = [r for r in case_run_results if not r["error"]]
    error_count = total - len(non_error)

    g2_checked = [r for r in non_error if any(c.name == "G2_no_invented_amounts" for c in r["checks"])]
    g2_failed = [
        r for r in g2_checked if any(c.name == "G2_no_invented_amounts" and not c.passed for c in r["checks"])
    ]
    invented_amount_rate = len(g2_failed) / len(g2_checked) if g2_checked else 0.0

    action_cases = [r for r in non_error if any(c.name == "expect_action" for c in r["checks"])]
    action_passes = [
        r for r in action_cases if any(c.name == "expect_action" and c.passed for c in r["checks"])
    ]
    action_accuracy = len(action_passes) / len(action_cases) if action_cases else 0.0

    g1_checked = [r for r in non_error if any(c.name == "G1_ai_disclosure" for c in r["checks"])]
    g1_passed = [r for r in g1_checked if any(c.name == "G1_ai_disclosure" and c.passed for c in r["checks"])]
    ai_disclosure_rate = len(g1_passed) / len(g1_checked) if g1_checked else 0.0

    all_latencies = [lat for r in case_run_results for lat in r["turn_latencies_ms"]]
    latency_p50 = nearest_rank_percentile(all_latencies, 50)
    latency_p95 = nearest_rank_percentile(all_latencies, 95)

    all_tokens_in = [t[0] for r in case_run_results for t in r["turn_tokens"]]
    all_tokens_out = [t[1] for r in case_run_results for t in r["turn_tokens"]]
    avg_tokens_in = sum(all_tokens_in) / len(all_tokens_in) if all_tokens_in else 0.0
    avg_tokens_out = sum(all_tokens_out) / len(all_tokens_out) if all_tokens_out else 0.0

    turns_per_conversation = (
        sum(len(r["turn_tokens"]) for r in case_run_results) / total if total else 0.0
    )
    mean_tokens_in_per_conv = avg_tokens_in * turns_per_conversation
    mean_tokens_out_per_conv = avg_tokens_out * turns_per_conversation
    cost_per_conv_inr = (
        mean_tokens_in_per_conv * (settings.eval.usd_per_1m_input_tokens / 1_000_000)
        + mean_tokens_out_per_conv * (settings.eval.usd_per_1m_output_tokens / 1_000_000)
    ) * settings.eval.inr_per_usd
    cost_per_100 = cost_per_conv_inr * 100

    return RunMetrics(
        pass_rate=pass_rate,
        category_pass_rate=category_pass_rate,
        invented_amount_rate=invented_amount_rate,
        error_count=error_count,
        action_accuracy=action_accuracy,
        ai_disclosure_rate=ai_disclosure_rate,
        latency_p50=latency_p50,
        latency_p95=latency_p95,
        avg_tokens_in=avg_tokens_in,
        avg_tokens_out=avg_tokens_out,
        cost_inr_per_100_conversations=cost_per_100,
    )


@dataclass
class AggregatedMetrics:
    mean: RunMetrics
    worst: RunMetrics
    flaky_cases: dict[str, str] = field(default_factory=dict)  # case_id -> "2/3"


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def aggregate_runs(run_metrics_list: list[RunMetrics], case_results_by_run: list[list[dict[str, Any]]]) -> AggregatedMetrics:
    all_categories: set[str] = set()
    for rm in run_metrics_list:
        all_categories.update(rm.category_pass_rate.keys())

    mean = RunMetrics(
        pass_rate=_mean([rm.pass_rate for rm in run_metrics_list]),
        category_pass_rate={
            cat: _mean([rm.category_pass_rate.get(cat, 0.0) for rm in run_metrics_list]) for cat in all_categories
        },
        invented_amount_rate=_mean([rm.invented_amount_rate for rm in run_metrics_list]),
        error_count=round(_mean([rm.error_count for rm in run_metrics_list])),
        action_accuracy=_mean([rm.action_accuracy for rm in run_metrics_list]),
        ai_disclosure_rate=_mean([rm.ai_disclosure_rate for rm in run_metrics_list]),
        latency_p50=_mean([rm.latency_p50 for rm in run_metrics_list]),
        latency_p95=_mean([rm.latency_p95 for rm in run_metrics_list]),
        avg_tokens_in=_mean([rm.avg_tokens_in for rm in run_metrics_list]),
        avg_tokens_out=_mean([rm.avg_tokens_out for rm in run_metrics_list]),
        cost_inr_per_100_conversations=_mean([rm.cost_inr_per_100_conversations for rm in run_metrics_list]),
    )

    worst_pass_rate = min(rm.pass_rate for rm in run_metrics_list)
    worst_invented = max(rm.invented_amount_rate for rm in run_metrics_list)
    worst_p95 = max(rm.latency_p95 for rm in run_metrics_list)
    worst = RunMetrics(
        pass_rate=worst_pass_rate,
        category_pass_rate={
            cat: min(rm.category_pass_rate.get(cat, 0.0) for rm in run_metrics_list) for cat in all_categories
        },
        invented_amount_rate=worst_invented,
        error_count=max(rm.error_count for rm in run_metrics_list),
        action_accuracy=min(rm.action_accuracy for rm in run_metrics_list),
        ai_disclosure_rate=min(rm.ai_disclosure_rate for rm in run_metrics_list),
        latency_p50=max(rm.latency_p50 for rm in run_metrics_list),
        latency_p95=worst_p95,
        avg_tokens_in=max(rm.avg_tokens_in for rm in run_metrics_list),
        avg_tokens_out=max(rm.avg_tokens_out for rm in run_metrics_list),
        cost_inr_per_100_conversations=max(rm.cost_inr_per_100_conversations for rm in run_metrics_list),
    )

    # Flaky cases: passed in some runs but not all.
    pass_counts: dict[str, int] = {}
    total_runs = len(case_results_by_run)
    for run_results in case_results_by_run:
        for r in run_results:
            pass_counts.setdefault(r["case_id"], 0)
            if r["passed"]:
                pass_counts[r["case_id"]] += 1

    flaky = {
        case_id: f"{count}/{total_runs}"
        for case_id, count in pass_counts.items()
        if 0 < count < total_runs
    }

    return AggregatedMetrics(mean=mean, worst=worst, flaky_cases=flaky)
