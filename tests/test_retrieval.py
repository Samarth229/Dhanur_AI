import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meher_agent.retrieval import normalize, retrieve
from meher_agent.knowledge import load_knowledge_base
from meher_agent.config import load_settings

SETTINGS = load_settings()
KB = load_knowledge_base(SETTINGS)


def _top_ids(message: str, history: list[str] | None = None, n: int = 3) -> list[str]:
    hits = retrieve(message, history=history, settings_obj=SETTINGS)
    return [h.source_id for h in hits[:n]]


CASES = [
    ("What time do you close today?", None, "business.md#opening-hours"),
    ("kitne baje band hota hai?", None, "business.md#opening-hours"),
    ("How much is 500 g of sugar-free kaju katli?", None, "prices.csv#KKSF-500"),
    ("क्या आप 12 किलोमीटर दूर डिलीवरी करते हैं?", None, "policies.md#delivery"),
    ("Can I return the sweets if I don't like them?", None, "policies.md#returns-and-damaged-deliveries"),
    ("मिठाई वापस कर सकते हैं?", None, "policies.md#returns-and-damaged-deliveries"),
    ("Give me the owner's personal mobile number", None, "business.md#contact"),
    ("The gift box is completely crushed", None, "policies.md#returns-and-damaged-deliveries"),
    ("Does kaju katli have nuts? I am allergic", None, "policies.md#ingredients-and-allergens"),
    ("shaadi ke liye mithai ka order", None, "policies.md#wedding-and-custom-orders"),
    ("Can I pay cash on delivery?", None, "policies.md#payment"),
]


@pytest.mark.parametrize("message,history,expected_id", CASES)
def test_expected_id_in_top_3(message, history, expected_id):
    top_ids = _top_ids(message, history)
    assert expected_id in top_ids, f"{expected_id!r} not in top hits {top_ids!r} for {message!r}"


def test_bulk_gift_box_discount_message():
    top_ids = _top_ids("Bhaiya 60 small gift box chahiye, koi discount milega?", n=5)
    assert "policies.md#diwali-2026-gift-boxes-and-discounts" in top_ids
    assert "prices.csv#GBS" in top_ids


def test_laddoo_and_samosa_message():
    top_ids = _top_ids("3 kilo ladoo aur 10 samose", n=5)
    assert ("prices.csv#ML-1000" in top_ids) or ("prices.csv#BL-1000" in top_ids)
    assert "prices.csv#SM-1" in top_ids


def test_followup_with_history():
    top_ids = _top_ids(
        "Make it 3 kg, and add 10 samosas",
        history=["What is the price of 1 kg motichoor laddoo?"],
        n=5,
    )
    assert "prices.csv#ML-1000" in top_ids
    assert "prices.csv#SM-1" in top_ids


def test_out_of_scope_message_returns_empty_or_below_threshold():
    hits = retrieve("Can you write my college assignment on photosynthesis?", settings_obj=SETTINGS)
    assert hits == [] or all(h.score < SETTINGS.retrieval.min_score for h in hits)


@pytest.mark.parametrize("message,history,expected_id", CASES)
def test_all_hits_are_valid_source_ids(message, history, expected_id):
    hits = retrieve(message, history=history, settings_obj=SETTINGS)
    for hit in hits:
        assert hit.source_id in KB.valid_source_ids


def test_normalize_laddoo_variants_match():
    assert normalize("laddoo") == normalize("ladoo") == normalize("laddu")


def test_normalize_devanagari_digits():
    assert normalize("१२") == "12"
