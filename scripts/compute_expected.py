"""Builds evals/cases.jsonl from evals/seed_cases.jsonl (copied verbatim)
plus evals/cases_src.jsonl (hand-written cases, with "compute" cases
getting their expected totals filled in by calling pricing.quote_order --
never hand-typed).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meher_agent.config import settings
from meher_agent.pricing import PricingError, quote_order
from evals_harness.checks import load_base_allowed_amounts

SEED_PATH = settings.paths.evals_dir / "seed_cases.jsonl"
SRC_PATH = settings.paths.evals_dir / "cases_src.jsonl"
OUT_PATH = settings.paths.evals_dir / "cases.jsonl"


def _read_seed_lines() -> list[str]:
    """Reads the seed file's lines as text, decoded from the exact same
    bytes that will be re-encoded on write, so the output is byte-identical
    to the original (verified by tests/test_cases_file.py)."""
    with open(SEED_PATH, "rb") as f:
        raw = f.read()
    lines = raw.splitlines(keepends=True)
    return [line.decode("utf-8") for line in lines if line.strip()]


def _resolve_quote_field(quote, field_name: str):
    if hasattr(quote, field_name):
        return getattr(quote, field_name)
    if hasattr(quote.bulk, field_name):
        return getattr(quote.bulk, field_name)
    raise AttributeError(f"OrderQuote has no field '{field_name}' (checked top-level and .bulk)")


def _apply_compute(case: dict, base_allowed: set[float]) -> tuple[dict, list[str]]:
    """Returns (updated_case, computed_values_for_table)."""
    compute = case["compute"]
    items = compute["items"]
    distance_km = compute.get("distance_km")
    delivery_date = compute.get("delivery_date")
    include_fields = compute.get("include", ["grand_total"])

    quote = quote_order(items, distance_km=distance_km, delivery_date=delivery_date)

    must_include = list(case.get("must_include", []))
    computed_values = []
    for field_name in include_fields:
        value = _resolve_quote_field(quote, field_name)
        str_value = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
        if str_value not in must_include:
            must_include.append(str_value)
        computed_values.append(str_value)
    case["must_include"] = must_include

    hand_written_allowed = {float(a) for a in case.get("allowed_amounts", [])}
    combined_allowed = set(quote.allowed_amounts) | hand_written_allowed
    case["allowed_amounts"] = sorted(combined_allowed - base_allowed)

    return case, computed_values


def build_cases_jsonl() -> tuple[list[str], list[tuple[str, list[str], list[float]]]]:
    """Returns (output_lines, table_rows) without writing anything."""
    seed_lines = _read_seed_lines()

    with open(SRC_PATH, encoding="utf-8") as f:
        src_lines = [line for line in f if line.strip()]

    base_allowed = set(load_base_allowed_amounts(settings.paths.data_dir))

    output_lines = list(seed_lines)
    table_rows: list[tuple[str, list[str], list[float]]] = []

    for line in src_lines:
        case = json.loads(line)
        if "compute" in case:
            case, computed_values = _apply_compute(case, base_allowed)
            table_rows.append((case["id"], computed_values, case["allowed_amounts"]))
        output_lines.append(json.dumps(case, ensure_ascii=False) + "\n")

    return output_lines, table_rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Build evals/cases.jsonl with computed totals.")
    parser.add_argument("--check", action="store_true", help="Exit non-zero if cases.jsonl is out of date.")
    args = parser.parse_args()

    try:
        output_lines, table_rows = build_cases_jsonl()
    except PricingError as exc:
        print(f"PricingError while computing a case: {exc.code}: {exc.message}")
        return 1

    new_content = "".join(output_lines)

    if args.check:
        if not OUT_PATH.exists() or OUT_PATH.read_text(encoding="utf-8") != new_content:
            print(f"{OUT_PATH} is out of date. Run: python manage.py cases")
            return 1
        print(f"{OUT_PATH} is up to date.")
        return 0

    with open(OUT_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(new_content)

    print(f"{'Case ID':<15} {'Computed values':<40} {'Allowed amounts'}")
    print("-" * 90)
    for case_id, values, allowed in table_rows:
        print(f"{case_id:<15} {', '.join(values):<40} {allowed}")

    print(f"\nWrote {len(output_lines)} cases to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
