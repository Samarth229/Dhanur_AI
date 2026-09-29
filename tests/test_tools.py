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


def make_ctx(conversation_id="conv-1", today=None, lead_store=None, escalation_store=None, customer_messages=None):
    return ToolContext(
        conversation_id=conversation_id,
        kb=KB,
        lexicon=LEXICON,
        settings=SETTINGS,
        lead_store=lead_store or LeadStore(),
        escalation_store=escalation_store or EscalationStore(),
        today=today or date(2026, 9, 28),
        customer_messages=customer_messages if customer_messages is not None else [],
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
        make_ctx(customer_messages=["I'm Amit, a@example.com"]),
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
    ctx = make_ctx(today=date(2026, 9, 28), customer_messages=["I'm Amit, a@example.com"])
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
        make_ctx(customer_messages=["I'm Amit, amit@example.com"]),
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
        make_ctx(
            today=date(2026, 9, 28),
            customer_messages=[
                "We need 30 large gift boxes for our office Diwali party on 3 November. "
                "I'm Ritu Malhotra, ritu.m@example.com"
            ],
        ),
    )
    assert result.ok is True
    assert result.action["args"]["email"] == "ritu.m@example.com"


# ---------------------------------------------------------------------------
# Upsert via the tool layer
# ---------------------------------------------------------------------------


def test_upsert_merges_across_two_calls_same_conversation():
    store = LeadStore()
    ctx = make_ctx(
        conversation_id="conv-x",
        lead_store=store,
        customer_messages=["I'm Amit, amit@example.com", "my phone is 9876543210"],
    )

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
        make_ctx(conversation_id="conv-a", lead_store=store, customer_messages=["I'm Amit, amit@example.com"]),
    )
    execute_tool(
        "save_lead",
        {"name": "Ritu", "need": "gift boxes", "phone": "9876543210"},
        make_ctx(conversation_id="conv-b", lead_store=store, customer_messages=["I'm Ritu, phone 9876543210"]),
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
        make_ctx(
            customer_messages=["2 kg kaju katli and one large gift box, delivered 5 km away, total?"]
        ),
    )
    assert result.ok is True
    assert result.action is None
    assert 3850 in result.data.allowed_amounts


# ---------------------------------------------------------------------------
# Fix 5a: email/phone grounding
# ---------------------------------------------------------------------------


def test_email_grounding_substitutes_single_customer_typed_value():
    # Model gives a mangled email, but the customer typed exactly one real one.
    result = execute_tool(
        "save_lead",
        {"name": "Neha Kapoor", "need": "custom boxes", "email": "neha@company.co.in"},
        make_ctx(customer_messages=["I'm Neha Kapoor, email Neha.K@Company.co.in"]),
    )
    assert result.ok is True
    assert result.action["args"]["email"] == "neha.k@company.co.in"


def test_email_grounding_rejects_when_no_customer_email_exists():
    result = execute_tool(
        "save_lead",
        {"name": "Amit", "need": "wedding order", "email": "amit@example.com"},
        make_ctx(customer_messages=["I'm Amit, please call me back"]),
    )
    assert result.ok is False
    assert "not given by the customer" in result.content


def test_phone_grounding_substitutes_single_customer_typed_value():
    result = execute_tool(
        "save_lead",
        {"name": "Amit Verma", "need": "wedding order", "phone": "9999999999"},
        make_ctx(customer_messages=["I'm Amit Verma, number 98765 43210."]),
    )
    assert result.ok is True
    assert result.action["args"]["phone"] == "9876543210"


def test_phone_grounding_rejects_when_no_customer_phone_exists():
    result = execute_tool(
        "save_lead",
        {"name": "Amit", "need": "wedding order", "phone": "9876543210"},
        make_ctx(customer_messages=["I'm Amit, no phone given"]),
    )
    assert result.ok is False
    assert "not given by the customer" in result.content


def test_email_grounding_passes_when_model_value_matches_customer_value():
    result = execute_tool(
        "save_lead",
        {"name": "Amit", "need": "wedding order", "email": "amit@example.com"},
        make_ctx(customer_messages=["I'm Amit, amit@example.com"]),
    )
    assert result.ok is True
    assert result.action["args"]["email"] == "amit@example.com"


# ---------------------------------------------------------------------------
# Fix 5b: name grounding (the lead-03 "Mr. Patel" hallucination scenario)
# ---------------------------------------------------------------------------


def test_name_grounding_rejects_hallucinated_name():
    # The model invents "Mr. Patel" -- the customer never said that name.
    result = execute_tool(
        "save_lead",
        {"name": "Mr. Patel", "need": "custom sweet boxes for a corporate event", "phone": "9876543210"},
        make_ctx(customer_messages=["We want custom sweet boxes for a corporate event next month."]),
    )
    assert result.ok is False
    assert "name was not given by the customer" in result.content


def test_name_grounding_passes_when_name_was_typed():
    result = execute_tool(
        "save_lead",
        {"name": "Neha Kapoor", "need": "custom boxes", "email": "neha.k@company.co.in"},
        make_ctx(customer_messages=["I'm Neha Kapoor, email Neha.K@Company.co.in. Around 40 boxes."]),
    )
    assert result.ok is True


def test_name_grounding_skipped_when_customer_wrote_devanagari():
    # The model transliterates a Hindi name into Roman script -- allowed.
    result = execute_tool(
        "save_lead",
        {"name": "Sunita Gupta", "need": "wedding order", "email": "sunita.g@example.com"},
        make_ctx(
            customer_messages=[
                "मेरी बेटी की शादी 20 दिसंबर को है, मेरा नाम सुनीता गुप्ता है, ईमेल sunita.g@example.com"
            ]
        ),
    )
    assert result.ok is True


def test_lead_04_invalid_phone_still_rejected_by_format_not_grounding():
    # "12345" is invalid on its own terms -- must fail with the phone-format
    # error, not a grounding error, and regardless never gets saved.
    result = execute_tool(
        "save_lead",
        {"name": "Rohit Sharma", "need": "wedding order for 200 guests", "phone": "12345"},
        make_ctx(customer_messages=["Wedding order for 200 guests. My name is Rohit Sharma, phone 12345."]),
    )
    assert result.ok is False


# ---------------------------------------------------------------------------
# Fix 9: calculate_order argument grounding
# ---------------------------------------------------------------------------


def test_item_grounding_rejects_unmentioned_item():
    # The hinglish-04 scenario: a pure policy question, no items mentioned,
    # but the model invents items to price.
    result = execute_tool(
        "calculate_order",
        {"items": [{"item": "Mixed Namkeen", "amount": 10, "unit": "pack"}]},
        make_ctx(customer_messages=["7000 ke order pe cash on delivery milega kya?"]),
    )
    assert result.ok is False
    assert "did not ask for" in result.content


def test_item_grounding_passes_for_mentioned_item():
    result = execute_tool(
        "calculate_order",
        {"items": [{"item": "kaju katli", "amount": 2, "unit": "kg"}]},
        make_ctx(customer_messages=["2 kg kaju katli please"]),
    )
    assert result.ok is True


def test_item_grounding_passes_across_turns():
    # arith-12-style: item named in an earlier turn, referenced as "that" later.
    result = execute_tool(
        "calculate_order",
        {"items": [{"item": "KKSF-500", "amount": 3, "unit": "pack"}]},
        make_ctx(
            customer_messages=[
                "Do you have sugar-free kaju katli?",
                "Great, give me 3 packs of that.",
            ]
        ),
    )
    assert result.ok is True


def test_item_grounding_accepts_literal_sku_mention():
    result = execute_tool(
        "calculate_order",
        {"items": [{"item": "GBL", "amount": 1, "unit": "box"}]},
        make_ctx(customer_messages=["I want one GBL"]),
    )
    assert result.ok is True


def test_item_grounding_accepts_plural_and_variant_item_names():
    # Hotfix: "samosas"/"samose" (already lexicon-covered) and "laddoos"
    # (added to the lexicon by this fix) must all ground correctly.
    for variant, message in [
        ("samosas", "10 samosas please"),
        ("samose", "10 samose chahiye"),
        ("motichoor laddoos", "1 kg motichoor laddoos please"),
    ]:
        result = execute_tool(
            "calculate_order",
            {"items": [{"item": variant, "amount": 1, "unit": "kg" if "laddoo" in variant else "piece"}]},
            make_ctx(customer_messages=[message]),
        )
        assert result.ok is True, f"{variant!r} should ground: {result.content}"


def test_distance_grounding_rejects_missing_distance():
    result = execute_tool(
        "calculate_order",
        {"items": [{"item": "kaju katli", "amount": 1, "unit": "kg"}]},
        make_ctx(customer_messages=["1 kg kaju katli delivered 5 km away"]),
    )
    assert result.ok is False
    assert "5 km" in result.content


def test_distance_grounding_rejects_wrong_distance():
    result = execute_tool(
        "calculate_order",
        {"items": [{"item": "kaju katli", "amount": 1, "unit": "kg"}], "distance_km": 3},
        make_ctx(customer_messages=["1 kg kaju katli delivered 5 km away"]),
    )
    assert result.ok is False
    assert "5 km" in result.content


def test_distance_grounding_passes_for_correct_distance():
    result = execute_tool(
        "calculate_order",
        {"items": [{"item": "kaju katli", "amount": 1, "unit": "kg"}], "distance_km": 5},
        make_ctx(customer_messages=["1 kg kaju katli delivered 5 km away"]),
    )
    assert result.ok is True


def test_distance_grounding_silent_when_not_mentioned():
    result = execute_tool(
        "calculate_order",
        {"items": [{"item": "kaju katli", "amount": 1, "unit": "kg"}]},
        make_ctx(customer_messages=["1 kg kaju katli please"]),
    )
    assert result.ok is True


HINDI_06_MESSAGES = [
    "रसमलाई की कीमत क्या है?",
    "2 पैक चाहिए, 4 किलोमीटर दूर भेज दीजिए।",
]


def test_unit_grounding_rejects_kg_for_pack_quantity():
    # The hindi-06 scenario: "2 पैक" (2 packs) sent as unit=kg.
    result = execute_tool(
        "calculate_order",
        {"items": [{"item": "rasmalai", "amount": 2, "unit": "kg"}], "distance_km": 4},
        make_ctx(customer_messages=HINDI_06_MESSAGES),
    )
    assert result.ok is False
    assert "packs" in result.content
    assert "'pack'" in result.content


def test_unit_grounding_passes_when_pack_used():
    result = execute_tool(
        "calculate_order",
        {"items": [{"item": "rasmalai", "amount": 2, "unit": "pack"}], "distance_km": 4},
        make_ctx(customer_messages=HINDI_06_MESSAGES),
    )
    assert result.ok is True
    assert result.data.grand_total == 740


def test_unit_grounding_ignores_pack_number_from_a_different_product():
    # Hotfix (turns 8/10 of the manual chat-page transcript): the customer
    # said "3 packs soan papdi" earlier, then later ordered "3 kg" of an
    # unrelated product (motichoor laddoo). The earlier pack number must not
    # leak into a completely different item's unit check just because the
    # amount happens to match.
    messages = [
        "3 packs soan papdi and 2 mixed namkeen, 10 km away",
        "What is the price of 1 kg motichoor laddoo?",
        "Make it 3 kg and add 10 samosas, deliver 2 km. Total?",
    ]
    result = execute_tool(
        "calculate_order",
        {
            "items": [
                {"item": "motichoor laddoo", "amount": 3, "unit": "kg"},
                {"item": "samosa", "amount": 10, "unit": "piece"},
            ],
            "distance_km": 2,
        },
        make_ctx(customer_messages=messages),
    )
    assert result.ok is True
    assert result.data.grand_total == 1880
