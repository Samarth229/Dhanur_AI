import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meher_agent.config import load_settings
from meher_agent.language import detect_language, normalize_digits

SETTINGS = load_settings()


def _load_seed_cases():
    cases = []
    with open(SETTINGS.paths.evals_dir / "seed_cases.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


SEED_CASES = _load_seed_cases()
SEED_EXPECTED_LANGUAGE = {
    "hindi-01": "hi",
    "hinglish-01": "hinglish",
}


@pytest.mark.parametrize("case", SEED_CASES, ids=[c["id"] for c in SEED_CASES])
def test_seed_case_language(case):
    expected = SEED_EXPECTED_LANGUAGE.get(case["id"], "en")
    last_turn = case["turns"][-1]
    assert detect_language(last_turn, settings_obj=SETTINGS) == expected


EXTRA_CASES = [
    ("kitne baje band hota hai", None, "hinglish"),
    ("How much is kaju katli?", None, "en"),
    ("Bhaiya 3 kilo motichoor laddoo chahiye", None, "hinglish"),
    ("मिठाई वापस कर सकते हैं?", None, "hi"),
    ("Can I pay cash on delivery?", None, "en"),
    ("Is there any discount on gift boxes?", None, "en"),
    ("Do you have samosas?", None, "en"),
    ("How much is kaju katli, bhaiya?", None, "en"),
    ("samose hai kya?", None, "hinglish"),
    ("mujhe 2 kg chahiye", None, "hinglish"),
    ("Thanks!", None, "en"),
    ("hello", None, "en"),
    ("Is this vegetarian?", None, "en"),
    ("kab tak deliver hoga", None, "hinglish"),
    ("What are your opening hours?", None, "en"),
]


@pytest.mark.parametrize("text,previous,expected", EXTRA_CASES)
def test_extra_language_cases(text, previous, expected):
    assert detect_language(text, previous, settings_obj=SETTINGS) == expected


def test_neutral_short_message_defers_to_previous():
    assert detect_language("3 kg", previous="hinglish", settings_obj=SETTINGS) == "hinglish"
    assert detect_language("ok", previous="hi", settings_obj=SETTINGS) == "hi"
    assert detect_language("yes", previous="en", settings_obj=SETTINGS) == "en"
    assert detect_language("thanks", previous=None, settings_obj=SETTINGS) == "en"


def test_devanagari_sentence_with_english_word_is_hindi():
    # A Devanagari sentence with the Latin word "delivery" mixed in.
    text = "हम आपकी delivery करते हैं अगर आप घर पर हों"
    assert detect_language(text, settings_obj=SETTINGS) == "hi"


def test_normalize_digits():
    assert normalize_digits("१२") == "12"
    assert normalize_digits("no digits here") == "no digits here"
