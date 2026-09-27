import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meher_agent import tools as tools_module
from meher_agent.config import load_settings
from meher_agent.knowledge import load_knowledge_base
from meher_agent.retrieval import load_lexicon
from meher_agent.stores import EscalationStore, LeadStore
from meher_agent.tools import TOOLS, ToolContext, execute_tool

SETTINGS = load_settings()
KB = load_knowledge_base(SETTINGS)
LEXICON = load_lexicon(SETTINGS)


def make_ctx(conversation_id="conv-1", today=None, lead_store=None, escalation_store=None):
    return ToolContext(
        conversation_id=conversation_id,
        kb=KB,
        lexicon=LEXICON,
        settings=SETTINGS,
        lead_store=lead_store or LeadStore(),
        escalation_store=escalation_store or EscalationStore(),
        today=today or date(2026, 9, 28),
    )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


def test_schemas_valid_and_unique_names():
    names = [t["function"]["name"] for t in TOOLS]
    assert len(names) == len(set(names)) == 3
    for t in TOOLS:
        assert "required" in t["function"]["parameters"]
        assert t["function"]["parameters"]["required"]


# ---------------------------------------------------------------------------
# Invalid arguments never raise, always ok=False with "ERROR:"
# ---------------------------------------------------------------------------


def test_malformed_json_string():
    result = execute_tool("calculate_order", "{not json", make_ctx())
    assert result.ok is False
    assert result.content.startswith("ERROR:")


def test_unknown_tool_name():
    result = execute_tool("does_not_exist", {}, make_ctx())
    assert result.ok is False
    assert result.content.startswith("ERROR:")


def test_save_lead_without_name():
    result = execute_tool("save_lead", {"need": "wedding order", "email": "a@example.com"}, make_ctx())
    assert result.ok is False
    assert result.content.startswith("ERROR:")


def test_save_lead_with_invalid_phone():
    result = execute_tool(
        "save_lead", {"name": "Amit", "need": "wedding order", "phone": "12345"}, make_ctx()
    )
    assert result.ok is False
    assert result.content.startswith("ERROR:")


def test_save_lead_without_contact_info():
    result = execute_tool("save_lead", {"name": "Amit", "need": "wedding order"}, make_ctx())
    assert result.ok is False
    assert result.content.startswith("ERROR:")


def test_save_lead_with_invalid_email():
    result = execute_tool(
        "save_lead", {"name": "Amit", "need": "wedding order", "email": "ritu@"}, make_ctx()
    )
    assert result.ok is False
    assert result.content.startswith("ERROR:")


def test_save_lead_with_wrong_date_format():
    result = execute_tool(
        "save_lead",
        {"name": "Amit", "need": "wedding order", "email": "a@example.com", "date": "03-11-2026"},
        make_ctx(),
    )
    assert result.ok is False
    assert result.content.startswith("ERROR:")


def test_escalate_with_empty_reason():
    result = execute_tool("escalate", {"reason": ""}, make_ctx())
    assert result.ok is False
    assert result.content.startswith("ERROR:")


def test_calculate_order_unknown_item():
    result = execute_tool(
        "calculate_order", {"items": [{"item": "rabri", "amount": 1, "unit": "kg"}]}, make_ctx()
    )
    assert result.ok is False
    assert result.content.startswith("ERROR:")


def test_calculate_order_empty_items():
    result = execute_tool("calculate_order", {"items": []}, make_ctx())
    assert result.ok is False
    assert result.content.startswith("ERROR:")


def test_calculate_order_non_numeric_amount():
    result = execute_tool(
        "calculate_order",
        {"items": [{"item": "kaju katli", "amount": "abc", "unit": "kg"}]},
        make_ctx(),
    )
    assert result.ok is False
    assert result.content.startswith("ERROR:")


def test_unexpected_exception_is_caught(monkeypatch):
    def boom(args, ctx):
        raise RuntimeError("boom")

    monkeypatch.setitem(tools_module._HANDLERS, "escalate", boom)
    result = execute_tool("escalate", {"reason": "test"}, make_ctx())
    assert result.ok is False
    assert result.content.startswith("ERROR:")
    assert result.action is None


# ---------------------------------------------------------------------------
# Past-date hint
# ---------------------------------------------------------------------------


def test_past_date_hint_gives_next_occurrence():
    ctx = make_ctx(today=date(2026, 9, 28))
    result = execute_tool(
        "save_lead",
        {"name": "Amit", "need": "wedding order", "email": "a@example.com", "date": "2025-11-03"},
        ctx,
    )
    assert result.ok is False
    assert "2026-11-03" in result.content


# ---------------------------------------------------------------------------
# Optional-field cleanup
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing_value", ["", "null", "none", "n/a", "unknown", "-"])
def test_optional_missing_values_treated_as_absent(missing_value):
    result = execute_tool(
        "save_lead",
        {
            "name": "Amit",
            "need": "wedding order",
            "email": "amit@example.com",
            "phone": missing_value,
            "quantity": missing_value,
            "date": missing_value,
        },
        make_ctx(),
    )
    assert result.ok is True


# ---------------------------------------------------------------------------
# Seed lead-01
# ---------------------------------------------------------------------------


def test_seed_lead_01():
    result = execute_tool(
        "save_lead",
        {
            "name": "Ritu Malhotra",
            "need": "30 large gift boxes for office Diwali party",
            "email": "Ritu.M@Example.com",
            "quantity": "30 boxes",
            "date": "2026-11-03",
        },
        make_ctx(today=date(2026, 9, 28)),
    )
    assert result.ok is True
    assert result.action["args"]["email"] == "ritu.m@example.com"


# ---------------------------------------------------------------------------
# Upsert via the tool layer
# ---------------------------------------------------------------------------


def test_upsert_merges_across_two_calls_same_conversation():
    store = LeadStore()
    ctx = make_ctx(conversation_id="conv-x", lead_store=store)

    r1 = execute_tool(
        "save_lead", {"name": "Amit", "need": "wedding order", "email": "amit@example.com"}, ctx
    )
    assert r1.ok is True
    assert "saved" in r1.content

    r2 = execute_tool("save_lead", {"name": "Amit", "need": "wedding order", "phone": "9876543210"}, ctx)
    assert r2.ok is True
    assert "updated" in r2.content

    leads = store.list_masked()
    assert len(leads) == 1
    assert leads[0]["email"] == "a*****@example.com"
    assert leads[0]["phone"] == "******3210"


def test_upsert_different_conversation_creates_second_lead():
    store = LeadStore()
    execute_tool(
        "save_lead",
        {"name": "Amit", "need": "wedding order", "email": "amit@example.com"},
        make_ctx(conversation_id="conv-a", lead_store=store),
    )
    execute_tool(
        "save_lead",
        {"name": "Ritu", "need": "gift boxes", "phone": "9876543210"},
        make_ctx(conversation_id="conv-b", lead_store=store),
    )
    assert len(store.list_masked()) == 2


# ---------------------------------------------------------------------------
# Escalate
# ---------------------------------------------------------------------------


def test_escalate_success():
    store = EscalationStore()
    ctx = make_ctx(escalation_store=store)
    result = execute_tool("escalate", {"reason": "Damaged delivery"}, ctx)
    assert result.ok is True
    assert result.handoff is True
    assert result.action["type"] == "escalate"
    assert len(store.list()) == 1


# ---------------------------------------------------------------------------
# calculate_order success
# ---------------------------------------------------------------------------


def test_calculate_order_success_no_action_and_allowed_amounts():
    result = execute_tool(
        "calculate_order",
        {
            "items": [
                {"item": "kaju katli", "amount": 2, "unit": "kg"},
                {"item": "GBL", "amount": 1, "unit": "box"},
            ],
            "distance_km": 5,
        },
        make_ctx(),
    )
    assert result.ok is True
    assert result.action is None
    assert 3850 in result.data.allowed_amounts
