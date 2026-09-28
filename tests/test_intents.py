import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meher_agent.config import load_settings
from meher_agent.intents import detect_intents

SETTINGS = load_settings()


@pytest.mark.parametrize(
    "text,expected_intent",
    [
        ("The gift box you delivered is completely crushed.", "complaint"),
        ("आपका डिब्बा टूटा हुआ आया है", "complaint"),
        ("The rasmalai tasted sour, I want to make a complaint.", "complaint"),
        ("Please connect me to a real person.", "human_request"),
        ("Malik ka number de do, main ek insaan se baat karna chahta hoon.", "human_request"),
        ("2 kg kaju katli, total kitna hoga?", "total"),
        ("कुल कितना होगा?", "total"),
    ],
)
def test_intent_detected(text, expected_intent):
    assert expected_intent in detect_intents(text, SETTINGS)


def test_damage_intent_subset_of_complaint_words():
    intents = detect_intents("The box arrived completely crushed and broken.", SETTINGS)
    assert "complaint" in intents
    assert "damage" in intents


def test_sour_complaint_is_not_damage():
    intents = detect_intents("The rasmalai tasted sour.", SETTINGS)
    assert "complaint" in intents
    assert "damage" not in intents


def test_false_positive_bad_alone_does_not_trigger_complaint():
    intents = detect_intents("Is kaju katli bad for diabetics?", SETTINGS)
    assert "complaint" not in intents


def test_no_intents_on_plain_product_question():
    intents = detect_intents("How much is 500 g of kaju katli?", SETTINGS)
    assert "complaint" not in intents
    assert "human_request" not in intents


def test_out_of_scope_message_has_no_complaint_intent():
    intents = detect_intents("Can you write my college assignment on photosynthesis?", SETTINGS)
    assert "complaint" not in intents
    assert "human_request" not in intents
