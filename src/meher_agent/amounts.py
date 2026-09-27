"""Rupee-amount extraction from free text.

extract_rupee_amounts_spec() implements exactly the task PDF's G2 rule (used
by the eval harness). extract_rupee_amounts_strict() extends it with extra
Devanagari/Hinglish rupee markers and Devanagari digits, for the agent's own
amount guard (Part 5).
"""
from __future__ import annotations

import re

from meher_agent.language import normalize_digits

# Matches a full grouped number (Western 3-3-3... or Indian 2-2-3 grouping)
# ending in exactly a 3-digit group, e.g. "3,850", "1,00,000", "1,23,45,678",
# "1,000,000". Deliberately does NOT match bare list-like commas such as
# "1,2" or "2, 3 and 4" (no digits directly after the comma there, or the
# group sizes don't fit a valid grouping).
_GROUPED_NUMBER_RE = re.compile(r"\b\d{1,3}(?:,\d{2,3})*,\d{3}(?:\.\d+)?\b")


def remove_thousands_separators(text: str) -> str:
    return _GROUPED_NUMBER_RE.sub(lambda m: m.group(0).replace(",", ""), text)


_NUMBER = r"[0-9]+(?:\.[0-9]+)?"

# PDF rule (G2): a rupee amount is a number after ₹, Rs, Rs. or INR
# (case-insensitive, optional space, word boundary before Rs/INR), or a
# number before "rupees".
_SPEC_PATTERN = re.compile(
    rf"₹\s*(?P<a1>{_NUMBER})"
    rf"|\bRs\.?\s*(?P<a2>{_NUMBER})"
    rf"|\bINR\s*(?P<a3>{_NUMBER})"
    rf"|(?P<a4>{_NUMBER})\s*rupees\b",
    re.IGNORECASE,
)

_STRICT_PATTERN = re.compile(
    rf"₹\s*(?P<a1>{_NUMBER})"
    rf"|\bRs\.?\s*(?P<a2>{_NUMBER})"
    rf"|\bINR\s*(?P<a3>{_NUMBER})"
    rf"|(?P<b1>{_NUMBER})\s*(?:रुपये|रुपए|रुपया|रु\.|रु)"
    rf"|\b(?P<b2>{_NUMBER})\s*(?:rupaye|rupay|rupiya|rupee|rupees)\b"
    rf"|(?P<b3>{_NUMBER})\s*/-",
    re.IGNORECASE,
)


def extract_rupee_amounts_spec(text: str) -> list[float]:
    text = remove_thousands_separators(text)
    amounts = []
    for match in _SPEC_PATTERN.finditer(text):
        value = next(g for g in match.groups() if g is not None)
        amounts.append(float(value))
    return amounts


def extract_rupee_amounts_strict(text: str) -> list[float]:
    text = normalize_digits(text)
    text = remove_thousands_separators(text)

    amounts = []
    for match in _STRICT_PATTERN.finditer(text):
        value = next(g for g in match.groups() if g is not None)
        amounts.append(float(value))
    return amounts


def is_amount_allowed(amount: float, allowed: set) -> bool:
    return float(amount) in {float(a) for a in allowed}
