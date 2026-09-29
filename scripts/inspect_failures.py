"""Reads reports/eval_report.json and prints, for every failing or flaky
case, each run's turns, final reply, actions (with args), and which checks
failed -- for root-causing baseline failures.

Note: the HTTP /chat response (and therefore this report) exposes actions
(save_lead/escalate, with args) but not raw tool-call names/arguments for
calculate_order -- that's internal to the agent and never crosses the HTTP
boundary. Where "did calculate_order get called, with what args" needs
answering, cross-reference the server's own log (meher_agent.agent logger
lines) for that run's conversation_id.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


def load_report(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def group_by_case(report: dict) -> dict[str, list[dict]]:
    by_case: dict[str, list[dict]] = {}
    for run in report["runs"]:
        for case_run in run:
            by_case.setdefault(case_run["case_id"], []).append(case_run)
    return by_case


def print_case_run(case_run: dict, run_index: int) -> None:
    print(f"  -- run {run_index} --")
    if case_run["error"]:
        print(f"    ERROR: {case_run['error_reason']}")
        return

    for i, turn in enumerate(case_run["turns"], start=1):
        response = turn.get("response") or {}
        print(f"    turn {i} message: {turn['request']['message']!r}")
        print(f"    turn {i} reply: {response.get('reply', '')!r}")
        actions = response.get("actions", [])
        if actions:
            print(f"    turn {i} actions: {actions}")
        print(f"    turn {i} sources: {response.get('sources', [])}")
        print(f"    turn {i} handoff: {response.get('handoff')}")

    failed_checks = [c for c in case_run["checks"] if not c["passed"]]
    if failed_checks:
        print("    FAILED checks:")
        for c in failed_checks:
            print(f"      - {c['name']}: {c['details']}")
    else:
        print("    (all checks passed this run)")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect failing/flaky cases from an eval report.")
    parser.add_argument(
        "--report", default="reports/eval_report.json", help="Path to eval_report.json (default: latest)."
    )
    args = parser.parse_args()

    report = load_report(Path(args.report))
    by_case = group_by_case(report)
    total_runs = len(report["runs"])

    print(f"Model: {report['meta']['model']}  Cases: {report['meta']['case_count']}  Runs: {total_runs}")
    print("=" * 90)

    interesting_cases = {
        case_id: runs for case_id, runs in by_case.items() if not all(r["passed"] for r in runs)
    }

    for case_id in sorted(interesting_cases):
        runs = interesting_cases[case_id]
        pass_count = sum(1 for r in runs if r["passed"])
        status = "FLAKY" if 0 < pass_count < total_runs else "ALWAYS FAILS"
        print(f"\n### {case_id} ({runs[0]['category']}) -- {status} ({pass_count}/{total_runs} passed)")
        for i, case_run in enumerate(runs, start=1):
            print_case_run(case_run, i)

    print("=" * 90)
    print(f"{len(interesting_cases)} case(s) with at least one failing run out of {len(by_case)} total.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
