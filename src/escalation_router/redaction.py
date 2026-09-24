"""Strip personal and payment data before anything is sent to the LLM.

Bug reports from support often contain donor emails, phone numbers or even
card numbers pasted from a screenshot. None of that is needed to route a bug.
"""

from __future__ import annotations

import re

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_CARD_CANDIDATE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{8,}\d(?!\w)")
_SECRET = re.compile(r"\b(?:sk|pk|rk|xox[abpr])[-_][A-Za-z0-9_-]{10,}\b")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _redact_card(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group())
    if 13 <= len(digits) <= 19 and _luhn_ok(digits):
        return "[CARD]"
    return match.group()


def _redact_phone(match: re.Match[str]) -> str:
    # Dates like 2026-09-01 match the pattern too; real phone numbers have 10+ digits.
    if len(re.sub(r"\D", "", match.group())) >= 10:
        return "[PHONE]"
    return match.group()


def redact(text: str) -> str:
    text = _SECRET.sub("[SECRET]", text)
    text = _EMAIL.sub("[EMAIL]", text)
    text = _CARD_CANDIDATE.sub(_redact_card, text)
    text = _PHONE.sub(_redact_phone, text)
    return text
