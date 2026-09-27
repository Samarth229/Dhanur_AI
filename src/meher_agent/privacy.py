"""Masking of contact details (email, phone) for logs and any customer-facing echo.

Never masks prices/amounts.
"""
from __future__ import annotations

import logging
import re

from meher_agent.validation import ValidationError, normalize_phone

_EMAIL_FIND_RE = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)

# Candidate spans that MIGHT be a phone number: digits with the separators
# normalize_phone already knows how to strip (space, dash, dot, parens),
# optionally prefixed with +. Commas are deliberately excluded so Indian
# thousands-grouped prices (e.g. "1,00,000") never enter this at all. Each
# candidate is then verified with normalize_phone before it is masked, so
# plain numbers (prices, quantities) are never mistaken for a phone number.
_PHONE_CANDIDATE_RE = re.compile(r"(?<![\d,])\+?[\d\s().-]{9,17}\d(?![\d,])")


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    first = local[0] if local else ""
    return f"{first}*****@{domain}"


def mask_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    last4 = digits[-4:] if len(digits) >= 4 else digits
    return "*" * 6 + last4


def _mask_if_phone(match: re.Match) -> str:
    candidate = match.group(0)
    try:
        digits = normalize_phone(candidate)
    except ValidationError:
        return candidate
    return mask_phone(digits)


def mask_text(text: str) -> str:
    text = _EMAIL_FIND_RE.sub(lambda m: mask_email(m.group(0)), text)
    text = _PHONE_CANDIDATE_RE.sub(_mask_if_phone, text)
    return text


class MaskingFilter(logging.Filter):
    """Logging filter that masks emails and phone numbers in log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: mask_text(v) if isinstance(v, str) else v for k, v in record.args.items()}
            else:
                record.args = tuple(
                    mask_text(arg) if isinstance(arg, str) else arg for arg in record.args
                )
        return True
