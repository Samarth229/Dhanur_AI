import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meher_agent.validation import (
    ValidationError,
    normalize_date,
    normalize_email,
    normalize_name,
    normalize_phone,
)

VALID_PHONES = [
    "+91 98765 43210",
    "+91-98765-43210",
    "098765 43210",
    "919876543210",
    "(987) 654-3210",
    "9876543210",
    "+919876543210",
    "91 9876543210",
]

INVALID_PHONES = [
    "12345",
    "01123456789",
    "5876543210",
    "abcdefghij",
    "98765432101",
    "987654321",
    "0000000000",
]


@pytest.mark.parametrize("raw", VALID_PHONES)
def test_valid_phones_normalize_to_expected(raw):
    assert normalize_phone(raw) == "9876543210"


@pytest.mark.parametrize("raw", INVALID_PHONES)
def test_invalid_phones_rejected(raw):
    with pytest.raises(ValidationError) as exc_info:
        normalize_phone(raw)
    assert exc_info.value.field == "phone"
    assert exc_info.value.message


VALID_EMAILS = [
    ("Ritu.M@Example.com", "ritu.m@example.com"),
    ("ritu+shop@example.com", "ritu+shop@example.com"),
    ("a.b@sub.example.co.in", "a.b@sub.example.co.in"),
]

INVALID_EMAILS = [
    "ritu@",
    "@x.com",
    "a..b@x.com",
    "ritu@example",
    "ritu m@x.com",
    ".ritu@x.com",
    "ritu.@x.com",
]


@pytest.mark.parametrize("raw,expected", VALID_EMAILS)
def test_valid_emails_normalize(raw, expected):
    assert normalize_email(raw) == expected


@pytest.mark.parametrize("raw", INVALID_EMAILS)
def test_invalid_emails_rejected(raw):
    with pytest.raises(ValidationError) as exc_info:
        normalize_email(raw)
    assert exc_info.value.field == "email"


def test_valid_names():
    assert normalize_name("  Amit   Verma ") == "Amit Verma"
    assert normalize_name("राहुल") == "राहुल"


@pytest.mark.parametrize("raw", ["", "   ", "12345", "x" * 101])
def test_invalid_names_rejected(raw):
    with pytest.raises(ValidationError) as exc_info:
        normalize_name(raw)
    assert exc_info.value.field == "name"


def test_valid_date():
    from datetime import date

    assert normalize_date("2026-11-03") == date(2026, 11, 3)


@pytest.mark.parametrize("raw", ["03-11-2026", "2026-02-30", "tomorrow", "2026/11/03"])
def test_invalid_dates_rejected(raw):
    with pytest.raises(ValidationError) as exc_info:
        normalize_date(raw)
    assert exc_info.value.field == "date"
