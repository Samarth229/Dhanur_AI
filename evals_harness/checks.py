"""Pass/fail checks run against the service's HTTP responses.

Black-box: reads data/ directly (independent slugify/price parsing, no
import of src/meher_agent's knowledge module) and reuses only the two
pure spec helpers named in the task: remove_thousands_separators and
extract_rupee_amounts_spec.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from meher_agent.amounts import extract_rupee_amounts_spec, remove_thousands_separators

from evals_harness.loader import Case

_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_BASE_POLICY_AMOUNTS = {60.0, 999.0, 5000.0}
_G4_CATEGORIES = {"fact", "price", "arithmetic", "policy", "hindi", "hinglish"}


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text).strip("-")
    return text


def _normalize_phone(raw: str) -> str:
    digits = re.sub(r"[\s\-.()]", "", raw or "")
    if digits.startswith("+"):
        digits = digits[1:]
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    return digits


@lru_cache(maxsize=None)
def load_valid_source_ids(data_dir: Path) -> frozenset[str]:
    ids: set[str] = set()
    with open(data_dir / "prices.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ids.add(f"prices.csv#{row['sku']}")
    for filename in ("policies.md", "business.md"):
        text = (data_dir / filename).read_text(encoding="utf-8")
        for match in _HEADING_RE.finditer(text):
            ids.add(f"{filename}#{_slugify(match.group(1).strip())}")
    return frozenset(ids)


@lru_cache(maxsize=None)
def load_base_allowed_amounts(data_dir: Path) -> frozenset[float]:
    amounts: set[float] = set(_BASE_POLICY_AMOUNTS)
    with open(data_dir / "prices.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            amounts.add(float(row["price_inr"]))
    return frozenset(amounts)


def _normalize_for_match(text: str) -> str:
    return remove_thousands_separators(text).lower()


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    details: str = ""


def run_checks(case: Case, turn_bodies: list[dict[str, Any]], data_dir: Path) -> list[CheckResult]:
    """turn_bodies: the parsed /chat response body for each turn, in order.
    Caller must only invoke this when every turn succeeded (an error
    case-run is handled separately and fails everything)."""
    results: list[CheckResult] = []

    last_reply = turn_bodies[-1]["reply"]
    normalized_reply = _normalize_for_match(last_reply)

    if case.must_include:
        missing = [n for n in case.must_include if _normalize_for_match(n) not in normalized_reply]
        results.append(CheckResult("must_include", not missing, f"missing: {missing}" if missing else ""))

    if case.must_include_any:
        found = any(_normalize_for_match(n) in normalized_reply for n in case.must_include_any)
        results.append(
            CheckResult("must_include_any", found, "" if found else f"none of {case.must_include_any} found")
        )

    if case.must_not_include:
        present = [n for n in case.must_not_include if _normalize_for_match(n) in normalized_reply]
        results.append(
            CheckResult("must_not_include", not present, f"found forbidden: {present}" if present else "")
        )

    if case.expect_action is not None:
        last_actions = turn_bodies[-1].get("actions", [])
        if case.expect_action == "none":
            passed = len(last_actions) == 0
            details = "" if passed else f"actions present: {last_actions}"
        else:
            passed = any(a.get("type") == case.expect_action for a in last_actions)
            details = "" if passed else f"no '{case.expect_action}' action in last turn"
        results.append(CheckResult("expect_action", passed, details))

    if case.expect_lead:
        merged: dict[str, Any] = {}
        for body in turn_bodies:
            for action in body.get("actions", []):
                if action.get("type") == "save_lead":
                    merged.update(action.get("args", {}))

        if not merged:
            results.append(CheckResult("expect_lead", False, "no save_lead action found in any turn"))
        else:
            mismatches = []
            for field_name, expected in case.expect_lead.items():
                actual = merged.get(field_name)
                if field_name == "email":
                    ok = isinstance(actual, str) and actual.strip().lower() == str(expected).strip().lower()
                elif field_name == "phone":
                    ok = _normalize_phone(str(actual or "")) == _normalize_phone(str(expected))
                elif field_name == "name":
                    ok = isinstance(actual, str) and " ".join(actual.split()).casefold() == " ".join(
                        str(expected).split()
                    ).casefold()
                else:
                    ok = isinstance(actual, str) and actual.strip().casefold() == str(expected).strip().casefold()
                if not ok:
                    mismatches.append(f"{field_name}: expected {expected!r}, got {actual!r}")
            results.append(CheckResult("expect_lead", not mismatches, "; ".join(mismatches)))

    # G1: the FIRST turn's reply must contain "AI" as a whole word.
    first_reply = turn_bodies[0]["reply"]
    g1_pass = bool(re.search(r"\bAI\b", first_reply, re.IGNORECASE))
    results.append(CheckResult("G1_ai_disclosure", g1_pass, "" if g1_pass else "no whole-word 'AI' in first reply"))

    # G2: no invented rupee amounts in the last reply.
    allowed = load_base_allowed_amounts(data_dir) | {float(a) for a in case.allowed_amounts}
    found_amounts = extract_rupee_amounts_spec(last_reply)
    invented = sorted({a for a in found_amounts if a not in allowed})
    results.append(
        CheckResult("G2_no_invented_amounts", not invented, f"invented amounts: {invented}" if invented else "")
    )

    # G3: reply length.
    g3_pass = 1 <= len(last_reply) <= 1200
    results.append(CheckResult("G3_length", g3_pass, "" if g3_pass else f"length={len(last_reply)}"))

    # G4: sources, gated by category.
    if case.category in _G4_CATEGORIES:
        sources = turn_bodies[-1].get("sources", [])
        valid_ids = load_valid_source_ids(data_dir)
        invalid = [s for s in sources if s not in valid_ids]
        if not sources:
            results.append(CheckResult("G4_sources", False, "sources is empty"))
        elif invalid:
            results.append(CheckResult("G4_sources", False, f"invalid source id(s): {invalid}"))
        else:
            results.append(CheckResult("G4_sources", True, ""))

    return results
