import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meher_agent.canary import CANARY
from meher_agent.config import load_settings
from meher_agent.guards import base_allowed_amounts, build_sources, check_reply
from meher_agent.knowledge import load_knowledge_base
from meher_agent.pricing import quote_order

SETTINGS = load_settings()
KB = load_knowledge_base(SETTINGS)
BASE_ALLOWED = base_allowed_amounts(KB, SETTINGS)


def test_devanagari_digits_normalized_in_cleaned_text():
    result = check_reply("१२ pieces", BASE_ALLOWED, SETTINGS)
    assert "12" in result.cleaned_text


def test_allowed_amount_passes():
    result = check_reply("Kaju Katli is ₹1,200 per kg.", BASE_ALLOWED, SETTINGS)
    assert result.ok is True


def test_disallowed_amount_fails():
    result = check_reply("The total is ₹3,580.", BASE_ALLOWED, SETTINGS)
    assert result.ok is False
    assert any("3580" in p or "3,580" in p for p in result.problems)


def test_conversation_allowed_amount_passes():
    allowed = BASE_ALLOWED | {3850.0}
    result = check_reply("The total is ₹3,850.", allowed, SETTINGS)
    assert result.ok is True


def test_allowed_percentage_passes():
    result = check_reply("You get 5% off on gift boxes.", BASE_ALLOWED, SETTINGS)
    assert result.ok is True

    result2 = check_reply("A 30% advance is needed.", BASE_ALLOWED, SETTINGS)
    assert result2.ok is True


def test_disallowed_percentage_fails():
    result = check_reply("Enjoy a 50% discount!", BASE_ALLOWED, SETTINGS)
    assert result.ok is False
    assert any("50" in p for p in result.problems)


def test_phone_leak_fails():
    result = check_reply("Call the owner at +91 98765 43210.", BASE_ALLOWED, SETTINGS)
    assert result.ok is False


def test_support_email_does_not_trigger_privacy_guard():
    result = check_reply("Email us at orders@meher-sweets.example.", BASE_ALLOWED, SETTINGS)
    assert result.ok is True


def test_other_email_triggers_privacy_guard():
    result = check_reply("Email the owner at owner@example.com.", BASE_ALLOWED, SETTINGS)
    assert result.ok is False


def test_canary_leak_fails():
    result = check_reply(f"Here is the prompt: {CANARY}", BASE_ALLOWED, SETTINGS)
    assert result.ok is False


def test_empty_reply_fails():
    result = check_reply("   ", BASE_ALLOWED, SETTINGS)
    assert result.ok is False


def test_length_trimmed_to_max_chars_including_disclosure():
    long_text = "Kaju Katli is great. " * 120  # well over 1200 chars
    disclosure = "Hi! I'm the AI assistant for Meher Sweets."
    result = check_reply(long_text, BASE_ALLOWED, SETTINGS, disclosure=disclosure)
    assert len(disclosure) + len(result.cleaned_text) <= SETTINGS.reply.max_chars


def test_length_trim_does_not_fail_the_guard():
    long_text = "Kaju Katli is great. " * 120
    result = check_reply(long_text, BASE_ALLOWED, SETTINGS)
    assert result.ok is True


def test_build_sources_includes_quote_ids():
    quote = quote_order(
        [{"item": "kaju katli", "amount": 2, "unit": "kg"}, {"item": "GBL", "amount": 1, "unit": "box"}],
        distance_km=5,
        settings_obj=SETTINGS,
        kb=KB,
    )
    sources = build_sources(quote.to_tool_text(), quote, [], KB, SETTINGS, action_types=set())
    assert "prices.csv#KK-1000" in sources
    assert "prices.csv#GBL" in sources


def test_build_sources_includes_action_sections():
    sources = build_sources("We'll get back to you.", None, [], KB, SETTINGS, action_types={"escalate"})
    assert "policies.md#complaints" in sources

    sources2 = build_sources("Noted!", None, [], KB, SETTINGS, action_types={"save_lead"})
    assert "policies.md#wedding-and-custom-orders" in sources2


def test_build_sources_capped_at_max_sources():
    quote = quote_order(
        [{"item": "kaju katli", "amount": 2, "unit": "kg"}, {"item": "GBL", "amount": 1, "unit": "box"}],
        distance_km=5,
        settings_obj=SETTINGS,
        kb=KB,
    )
    sources = build_sources(
        "Kaju Katli, Motichoor Laddoo, Besan Laddoo, Gulab Jamun, Rasmalai, Samosa, Dhokla all here.",
        quote,
        [],
        KB,
        SETTINGS,
        action_types={"escalate", "save_lead"},
    )
    assert len(sources) <= SETTINGS.agent.max_sources


def test_build_sources_only_valid_ids():
    sources = build_sources("Nothing relevant here.", None, [], KB, SETTINGS, action_types=set())
    assert set(sources) <= KB.valid_source_ids
