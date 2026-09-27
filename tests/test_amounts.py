import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meher_agent.amounts import (
    extract_rupee_amounts_spec,
    extract_rupee_amounts_strict,
    is_amount_allowed,
    remove_thousands_separators,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("3,850", "3850"),
        ("1,000,000", "1000000"),
        ("1,00,000", "100000"),
        ("1,23,45,678", "12345678"),
        ("2, 3 and 4", "2, 3 and 4"),
        ("1,2", "1,2"),
    ],
)
def test_remove_thousands_separators(text, expected):
    assert remove_thousands_separators(text) == expected


SPEC_CASES = [
    ("Total ₹3,850", [3850]),
    ("Rs. 1,00,000", [100000]),
    ("INR 780 and 60 rupees", [780, 60]),
    ("rs 240", [240]),
    ("3 kg costs ₹1,680", [1680]),
    ("we deliver within 8 km", []),
    ("₹ 37,050", [37050]),
    ("Rs.620", [620]),
    ("hers 50 rupees are safe", [50]),
]


@pytest.mark.parametrize("text,expected", SPEC_CASES)
def test_extract_rupee_amounts_spec(text, expected):
    assert extract_rupee_amounts_spec(text) == [float(e) for e in expected]


def test_hers_does_not_match_rs():
    assert extract_rupee_amounts_spec("hers 50") == []


def test_strict_devanagari_amount():
    result = extract_rupee_amounts_strict("कुल ₹१२०० rupaye")
    assert result == [1200.0]


def test_strict_devanagari_amount_pdf_example():
    # "कुल ₹३,८५०" = "kul ₹3,850" (Devanagari digits)
    result = extract_rupee_amounts_strict("कुल ₹३,८५०")
    assert result == [3850.0]


def test_strict_rupaye_marker():
    assert extract_rupee_amounts_strict("780 रुपये") == [780.0]


def test_strict_slash_suffix():
    assert extract_rupee_amounts_strict("560/-") == [560.0]


def test_strict_rupaye_word():
    assert extract_rupee_amounts_strict("1200 rupaye") == [1200.0]


def test_strict_devanagari_digits_with_comma():
    # "कुल ₹१,४००" = "kul ₹1,400" (Devanagari digits, comma-grouped)
    result = extract_rupee_amounts_strict("कुल ₹१,४००")
    assert result == [1400.0]


def test_spec_does_not_pick_up_devanagari_rupee_word():
    assert extract_rupee_amounts_spec("780 रुपये") == []


@pytest.mark.parametrize(
    "amount,allowed,expected",
    [
        (3850.0, {3850}, True),
        (3850, {3850.0}, True),
        (100, {200, 300}, False),
    ],
)
def test_is_amount_allowed(amount, allowed, expected):
    assert is_amount_allowed(amount, allowed) is expected
