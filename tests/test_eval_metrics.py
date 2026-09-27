import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from evals_harness.checks import CheckResult
from evals_harness.metrics import aggregate_runs, compute_run_metrics, nearest_rank_percentile
from meher_agent.config import load_settings

SETTINGS = load_settings()


def make_case_run(case_id, category, passed, error=False, checks=None, latencies=None, tokens=None):
    return {
        "case_id": case_id,
        "category": category,
        "error": error,
        "passed": passed,
        "checks": checks if checks is not None else [],
        "turn_latencies_ms": latencies or [100.0],
        "turn_tokens": tokens or [(100, 50)],
    }


def test_nearest_rank_percentile():
    values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    assert nearest_rank_percentile(values, 50) == 50
    assert nearest_rank_percentile(values, 95) == 100
    assert nearest_rank_percentile([], 50) == 0.0
    assert nearest_rank_percentile([42], 95) == 42


def test_compute_run_metrics_pass_rate_and_category():
    results = [
        make_case_run("c1", "price", True),
        make_case_run("c2", "price", False),
        make_case_run("c3", "policy", True),
    ]
    metrics = compute_run_metrics(results, SETTINGS)
    assert metrics.pass_rate == 2 / 3
    assert metrics.category_pass_rate["price"] == 0.5
    assert metrics.category_pass_rate["policy"] == 1.0


def test_compute_run_metrics_error_case_excluded_from_g2_rate():
    results = [
        make_case_run("c1", "price", True, checks=[CheckResult("G2_no_invented_amounts", True)]),
        make_case_run("c2", "price", False, checks=[CheckResult("G2_no_invented_amounts", False)]),
        make_case_run("c3", "price", False, error=True, checks=None),
    ]
    metrics = compute_run_metrics(results, SETTINGS)
    # only 2 non-error case-runs had G2 checked; 1 of them failed.
    assert metrics.invented_amount_rate == 0.5
    assert metrics.error_count == 1
    # overall pass rate still counts the error as a fail out of 3.
    assert metrics.pass_rate == 1 / 3


def test_compute_run_metrics_action_accuracy():
    results = [
        make_case_run("c1", "lead", True, checks=[CheckResult("expect_action", True)]),
        make_case_run("c2", "lead", False, checks=[CheckResult("expect_action", False)]),
        make_case_run("c3", "fact", True, checks=[]),  # no expect_action set
    ]
    metrics = compute_run_metrics(results, SETTINGS)
    assert metrics.action_accuracy == 0.5


def test_compute_run_metrics_ai_disclosure_rate():
    results = [
        make_case_run("c1", "fact", True, checks=[CheckResult("G1_ai_disclosure", True)]),
        make_case_run("c2", "fact", True, checks=[CheckResult("G1_ai_disclosure", False)]),
    ]
    metrics = compute_run_metrics(results, SETTINGS)
    assert metrics.ai_disclosure_rate == 0.5


def test_compute_run_metrics_cost_with_nonzero_prices():
    import dataclasses

    settings_with_price = dataclasses.replace(
        SETTINGS,
        eval=dataclasses.replace(SETTINGS.eval, usd_per_1m_input_tokens=1.0, usd_per_1m_output_tokens=2.0, inr_per_usd=100),
    )
    results = [make_case_run("c1", "fact", True, tokens=[(1000, 500)])]
    metrics = compute_run_metrics(results, settings_with_price)
    # 1 conversation, 1 turn: tokens_in=1000, tokens_out=500
    # cost per conv = (1000 * 1/1e6 + 500 * 2/1e6) * 100 = (0.001 + 0.001) * 100 = 0.2
    # cost per 100 conversations = 0.2 * 100 = 20
    assert round(metrics.cost_inr_per_100_conversations, 2) == 20.0


def test_aggregate_runs_mean_and_worst():
    run1 = [make_case_run("c1", "price", True), make_case_run("c2", "price", True)]
    run2 = [make_case_run("c1", "price", True), make_case_run("c2", "price", False)]
    m1 = compute_run_metrics(run1, SETTINGS)
    m2 = compute_run_metrics(run2, SETTINGS)
    aggregated = aggregate_runs([m1, m2], [run1, run2])
    assert aggregated.mean.pass_rate == (1.0 + 0.5) / 2
    assert aggregated.worst.pass_rate == 0.5


def test_aggregate_runs_flaky_cases():
    run1 = [make_case_run("c1", "price", True), make_case_run("c2", "price", True)]
    run2 = [make_case_run("c1", "price", True), make_case_run("c2", "price", False)]
    run3 = [make_case_run("c1", "price", True), make_case_run("c2", "price", True)]
    m = [compute_run_metrics(r, SETTINGS) for r in (run1, run2, run3)]
    aggregated = aggregate_runs(m, [run1, run2, run3])
    assert aggregated.flaky_cases == {"c2": "2/3"}
    assert "c1" not in aggregated.flaky_cases
