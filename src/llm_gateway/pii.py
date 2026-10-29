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

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("CREDIT_CARD", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("PHONE", re.compile(r"\b(?:\+?1[ -]?)?\(?\d{3}\)?[ -]?\d{3}[ -]?\d{4}\b")),
    ("IP", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
)


@dataclass(frozen=True)
class RedactionReport:
    """The redacted text and a count of replacements by PII type."""

    text: str
    counts: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def redact(text: str) -> RedactionReport:
    """Replace PII in ``text`` with typed placeholders and count replacements."""

    counts: dict[str, int] = {}
    redacted = text
    for label, pattern in _PATTERNS:
        matches = pattern.findall(redacted)
        if matches:
            counts[label] = counts.get(label, 0) + len(matches)
            redacted = pattern.sub(f"[{label}]", redacted)
    return RedactionReport(text=redacted, counts=counts)


def contains_pii(text: str) -> bool:
    """Return whether ``text`` contains any detectable PII."""

    return redact(text).total > 0
