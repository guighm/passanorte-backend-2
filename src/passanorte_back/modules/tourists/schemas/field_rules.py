"""Field validation rules for the ``tourists`` module (research R6).

Exact rules from the spec clarifications (FR-001/FR-002/FR-005a/FR-013*):

- ``normalize_cpf``/``is_valid_cpf``: masked or unmasked input, normalized
  to 11 digits, official check-digit algorithm (weights 10..2, two rounds).
- ``validate_passport_number``: ``^[A-Za-z0-9]{6,10}$``.
- ``validate_phone``: ``^\\+[0-9]{8,15}$`` (E.164-ish — no ``+DDI`` rejected).
- ``normalize_email``: trim + casefold before compare/persist.
- Free texts (first/last name, country): 1-100 chars after trim.
- Password: schema enforces at least 8 chars (FR-005a).
"""

import re
from typing import Final

PASSPORT_PATTERN: Final[str] = r"^[A-Za-z0-9]{6,10}$"
PHONE_PATTERN: Final[str] = r"^\+[0-9]{8,15}$"
MIN_PASSWORD_LENGTH: Final[int] = 8
TEXT_MAX_LENGTH: Final[int] = 100

_PASSPORT_RE = re.compile(PASSPORT_PATTERN)
_PHONE_RE = re.compile(PHONE_PATTERN)


def normalize_cpf(raw: str) -> str:
    """Normalize CPF input (masked or not) to 11 digits (FR-013c)."""
    return re.sub(r"\D", "", raw)


def is_valid_cpf(digits: str) -> bool:
    """Official check-digit algorithm (two rounds, weights descending)."""
    if len(digits) != 11 or not digits.isdigit():
        return False
    if len(set(digits)) == 1:  # all-equal digit sequences never valid
        return False

    def _check_digit(prefix: str, weights) -> int:
        total = sum(int(digit) * weight for digit, weight in zip(prefix, weights, strict=True))
        remainder = (total * 10) % 11
        return remainder if remainder < 10 else 0

    first = _check_digit(digits[:9], range(10, 1, -1))  # weights 10..2
    second = _check_digit(digits[:10], range(11, 1, -1))  # weights 11..2
    return digits[-2:] == f"{first}{second}"


def validate_cpf_value(value: str) -> str:
    """Normalized cpf or ValueError (Pydantic field validators call this)."""
    digits = normalize_cpf(value)
    if not is_valid_cpf(digits):
        raise ValueError("invalid cpf: 11 digits with valid check digits required")
    return digits


def validate_passport_value(value: str) -> str:
    if not _PASSPORT_RE.fullmatch(value):
        raise ValueError("invalid passport_number: alphanumeric with 6-10 characters required")
    return value


def validate_phone_value(value: str) -> str:
    if not _PHONE_RE.fullmatch(value):
        raise ValueError('invalid phone: international "+<digits>" format required (8-15 digits)')
    return value


def normalize_email(value: str) -> str:
    """Email normalized (trim + casefold) before compare/persist (FR-013)."""
    return value.strip().casefold()


def validate_text_length(value: str, *, field: str) -> str:
    """1-100 chars after trim (FR-013a/d)."""
    stripped = value.strip()
    if not 1 <= len(stripped) <= TEXT_MAX_LENGTH:
        raise ValueError(f"invalid {field}: 1-100 characters required after trimming")
    return stripped
