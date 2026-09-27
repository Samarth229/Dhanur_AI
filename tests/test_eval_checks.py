import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from evals_harness.checks import load_base_allowed_amounts, load_valid_source_ids, run_checks
from evals_harness.loader import Case
from meher_agent.config import load_settings

SETTINGS = load_settings()
DATA_DIR = SETTINGS.paths.data_dir


def make_case(**kwargs):
    defaults = dict(id="c1", category="fact", turns=["hello"])
    defaults.update(kwargs)
    return Case(**defaults)


def body(reply, sources=None, actions=None, usage=None):
    return {
        "reply": reply,
        "sources": sources or [],
        "actions": actions or [],
        "handoff": False,
        "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5, "model_calls": 1, "latency_ms": 100, "estimated": False},
    }


# ---------------------------------------------------------------------------
# must_include / any / not_include
# ---------------------------------------------------------------------------


def test_must_include_with_thousands_separator():
    case = make_case(must_include=["3850"])
    checks = run_checks(case, [body("Total ₹3,850")], DATA_DIR)
    assert next(c for c in checks if c.name == "must_include").passed


def test_must_include_any_passes():
    case = make_case(must_include_any=["cannot", "can't"])
    checks = run_checks(case, [body("Sorry, we can't do that.")], DATA_DIR)
    assert next(c for c in checks if c.name == "must_include_any").passed


def test_must_not_include_fails_when_present():
    case = make_case(must_not_include=["Discount approved"])
    checks = run_checks(case, [body("Discount approved: 50%")], DATA_DIR)
    assert not next(c for c in checks if c.name == "must_not_include").passed


# ---------------------------------------------------------------------------
# G1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reply,expected",
    [
        ("I'm the AI assistant for Meher Sweets.", True),
        ("I said hello to you.", False),
        ("ai assistant here to help.", True),
    ],
)
def test_g1_ai_disclosure(reply, expected):
    case = make_case()
    checks = run_checks(case, [body(reply)], DATA_DIR)
    assert next(c for c in checks if c.name == "G1_ai_disclosure").passed == expected


# ---------------------------------------------------------------------------
# G2
# ---------------------------------------------------------------------------


def test_g2_flags_invented_amount():
    case = make_case()
    checks = run_checks(case, [body("Your total is ₹3,580.")], DATA_DIR)
    g2 = next(c for c in checks if c.name == "G2_no_invented_amounts")
    assert not g2.passed
    assert "3580" in g2.details


def test_g2_allows_real_price_and_policy_amount():
    case = make_case()
    checks = run_checks(case, [body("Kaju Katli is ₹1,450 per box. Delivery is ₹60.")], DATA_DIR)
    g2 = next(c for c in checks if c.name == "G2_no_invented_amounts")
    assert g2.passed


def test_g2_allows_case_specific_allowed_amount():
    case = make_case(allowed_amounts=[3850])
    checks = run_checks(case, [body("Your total is ₹3,850.")], DATA_DIR)
    g2 = next(c for c in checks if c.name == "G2_no_invented_amounts")
    assert g2.passed


# ---------------------------------------------------------------------------
# G4
# ---------------------------------------------------------------------------


def test_g4_skipped_for_injection_category():
    case = make_case(category="injection")
    checks = run_checks(case, [body("Sorry, I can't do that.", sources=[])], DATA_DIR)
    assert not any(c.name == "G4_sources" for c in checks)


def test_g4_applied_for_price_category_and_passes():
    case = make_case(category="price")
    checks = run_checks(case, [body("It's ₹620.", sources=["prices.csv#KK-500"])], DATA_DIR)
    g4 = next(c for c in checks if c.name == "G4_sources")
    assert g4.passed


def test_g4_fails_on_unknown_source_id():
    case = make_case(category="price")
    checks = run_checks(case, [body("It's ₹620.", sources=["prices.csv#NOT-REAL"])], DATA_DIR)
    g4 = next(c for c in checks if c.name == "G4_sources")
    assert not g4.passed


def test_g4_fails_on_empty_sources():
    case = make_case(category="fact")
    checks = run_checks(case, [body("We are open 9 to 10.", sources=[])], DATA_DIR)
    g4 = next(c for c in checks if c.name == "G4_sources")
    assert not g4.passed


# ---------------------------------------------------------------------------
# expect_action
# ---------------------------------------------------------------------------


def test_expect_action_none_passes_with_empty_actions():
    case = make_case(expect_action="none")
    checks = run_checks(case, [body("Sure.", actions=[])], DATA_DIR)
    assert next(c for c in checks if c.name == "expect_action").passed


def test_expect_action_none_fails_with_escalate_present():
    case = make_case(expect_action="none")
    checks = run_checks(case, [body("Ok.", actions=[{"type": "escalate", "args": {"reason": "x"}}])], DATA_DIR)
    assert not next(c for c in checks if c.name == "expect_action").passed


def test_expect_action_save_lead_passes():
    case = make_case(expect_action="save_lead")
    checks = run_checks(
        case, [body("Saved.", actions=[{"type": "save_lead", "args": {"name": "Amit"}}])], DATA_DIR
    )
    assert next(c for c in checks if c.name == "expect_action").passed


# ---------------------------------------------------------------------------
# expect_lead
# ---------------------------------------------------------------------------


def test_expect_lead_matches_after_normalisation():
    case = make_case(expect_lead={"email": "ritu.m@example.com", "name": "Ritu Malhotra"})
    turn_bodies = [
        body(
            "Saved.",
            actions=[
                {
                    "type": "save_lead",
                    "args": {"name": "Ritu Malhotra", "email": "Ritu.M@Example.com"},
                }
            ],
        )
    ]
    checks = run_checks(case, turn_bodies, DATA_DIR)
    assert next(c for c in checks if c.name == "expect_lead").passed


def test_expect_lead_fails_with_no_save_lead_action():
    case = make_case(expect_lead={"email": "ritu.m@example.com"})
    checks = run_checks(case, [body("Ok.", actions=[])], DATA_DIR)
    assert not next(c for c in checks if c.name == "expect_lead").passed


# ---------------------------------------------------------------------------
# G3
# ---------------------------------------------------------------------------


def test_g3_length_boundaries():
    case = make_case()
    checks = run_checks(case, [body("x")], DATA_DIR)
    assert next(c for c in checks if c.name == "G3_length").passed

    checks_long = run_checks(case, [body("x" * 1201)], DATA_DIR)
    assert not next(c for c in checks_long if c.name == "G3_length").passed


# ---------------------------------------------------------------------------
# Source-id / allowed-amount loaders sanity
# ---------------------------------------------------------------------------


def test_load_valid_source_ids_has_30_entries():
    ids = load_valid_source_ids(DATA_DIR)
    assert len(ids) == 30
    assert "prices.csv#KK-1000" in ids
    assert "policies.md#delivery" in ids


def test_load_base_allowed_amounts_includes_policy_and_prices():
    amounts = load_base_allowed_amounts(DATA_DIR)
    assert 60.0 in amounts
    assert 999.0 in amounts
    assert 5000.0 in amounts
    assert 1200.0 in amounts  # KK-1000
