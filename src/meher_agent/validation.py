"""Phone, email, name and date validation/normalisation.

Each function returns a normalised value or raises ValidationError with a
message clear enough to relay back to the model / customer.
"""
from __future__ import annotations

import re
from datetime import date, datetime

_PHONE_JUNK_RE = re.compile(r"[\s\-.()]")
_PHONE_VALID_RE = re.compile(r"^[6-9]\d{9}$")

_EMAIL_RE = re.compile(
    r"^(?!\.)(?!.*\.\.)[A-Za-z0-9._%+-]+(?<!\.)@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*"
    r"\.[A-Za-z]{2,}$"
)

_NAME_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)


class ValidationError(Exception):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


def normalize_phone(raw: str) -> str:
    digits = _PHONE_JUNK_RE.sub("", raw)
    digits = digits.replace("+", "") if digits.startswith("+") else digits

    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]

    if not _PHONE_VALID_RE.match(digits):
        raise ValidationError(
            "phone",
            "That doesn't look like a valid Indian mobile number. "
            "Please share a 10-digit number starting with 6-9.",
        )
    return digits


def normalize_email(raw: str) -> str:
    email = raw.strip().lower()
    if len(email) > 254 or not _EMAIL_RE.match(email):
        raise ValidationError("email", "That doesn't look like a valid email address.")
    return email


def normalize_name(raw: str) -> str:
    name = " ".join(raw.strip().split())
    if not (1 <= len(name) <= 100):
        raise ValidationError("name", "Please share a name between 1 and 100 characters.")
    if not _NAME_LETTER_RE.search(name):
        raise ValidationError("name", "Please share a valid name.")
    return name


def normalize_date(raw: str, today: date | None = None) -> date:
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", raw.strip()):
        raise ValidationError("date", "Please share the date as YYYY-MM-DD.")
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError("date", "That isn't a real calendar date.")
