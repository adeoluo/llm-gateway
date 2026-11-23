"""Detection and redaction of personally identifiable information.

The gateway redacts common PII before a prompt reaches the model and can redact it
again from the model's response. Detection is regex-based for high-signal formats:
email addresses, phone numbers, United States social security numbers, credit-card
numbers, and IP addresses. Each match is replaced with a typed placeholder so the
text stays readable and the redaction is auditable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_CARD_RE = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("SSN", re.compile(r"\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")),
    ("PHONE", re.compile(r"\b(?:\+?1[ -]?)?\(?\d{3}\)?[ -]?\d{3}[ -]\d{4}\b")),
    (
        "IP",
        re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"),
    ),
    (
        "DOB",
        re.compile(r"(?i)\b(?:dob|date of birth|born on)[:\s]+\d{1,4}[-/]\d{1,2}[-/]\d{2,4}\b"),
    ),
    ("PASSPORT", re.compile(r"(?i)\bpassport(?:\s*(?:no|number|#))?[:\s]+[A-Z0-9]{6,9}\b")),
    (
        "API_KEY",
        re.compile(r"\b(?:sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,})\b"),
    ),
)


def _luhn_valid(text: str) -> bool:
    digits = [ord(c) - 48 for c in text if "0" <= c <= "9"]
    if not (13 <= len(digits) <= 19):
        return False
    if len(set(digits)) == 1:
        return False
    total = 0
    for idx, d in enumerate(reversed(digits)):
        if idx % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


@dataclass(frozen=True)
class RedactionReport:
    """The redacted text and a count of replacements by PII type."""

    text: str
    counts: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def redact(text: str) -> RedactionReport:
    """Replace structured PII and secrets in ``text`` with typed placeholders.

    Credit cards require a valid Luhn check digit so 13-19 digit order or tracking IDs
    are not falsely redacted; free-form person names require NER (out of scope for this
    zero-dependency regex stage).
    """

    counts: dict[str, int] = {}

    def _replace_card(match: re.Match[str]) -> str:
        raw = match.group(0)
        if _luhn_valid(raw):
            counts["CREDIT_CARD"] = counts.get("CREDIT_CARD", 0) + 1
            return "[CREDIT_CARD]"
        return raw

    redacted = _CARD_RE.sub(_replace_card, text)
    for label, pattern in _PATTERNS:
        matches = pattern.findall(redacted)
        if matches:
            counts[label] = counts.get(label, 0) + len(matches)
            redacted = pattern.sub(f"[{label}]", redacted)
    return RedactionReport(text=redacted, counts=counts)


def contains_pii(text: str) -> bool:
    """Return whether ``text`` contains any detectable structured PII."""

    return redact(text).total > 0
