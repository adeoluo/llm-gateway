"""Prompt-injection detection over user input.

Prompt injection is an input that tries to override the system's instructions or
extract its prompt. There is no perfect detector, so this is a layered set of
high-signal rules: instruction-override phrases ("ignore previous instructions"),
role reassignment ("you are now DAN"), system-prompt extraction ("repeat the words
above"), and delimiter or jailbreak markers. Each match contributes to a risk
score; a request is blocked when the score crosses a threshold.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERNS: tuple[tuple[re.Pattern[str], float, str], ...] = (
    (
        re.compile(r"(?i)ignore (all |the )?(previous|prior|above) (instructions|prompts?)"),
        1.0,
        "instruction_override",
    ),
    (re.compile(r"(?i)disregard (all |the )?(previous|prior|above|your) "), 0.8, "disregard"),
    (re.compile(r"(?i)you are now\b"), 0.7, "role_reassignment"),
    (
        re.compile(
            r"(?i)\b(act as|pretend to be|roleplay as)\b.{0,40}\b(dan|developer mode|jailbreak)\b"
        ),
        1.0,
        "jailbreak_persona",
    ),
    (
        re.compile(
            r"(?i)(repeat|print|reveal|show) (the )?(words |text )?"
            r"(above|your (system )?prompt|previous instructions)"
        ),
        1.0,
        "prompt_extraction",
    ),
    (re.compile(r"(?i)\bsystem prompt\b"), 0.5, "mentions_system_prompt"),
    (re.compile(r"(?i)\bdeveloper mode\b"), 0.6, "developer_mode"),
    (re.compile(r"(?i)do anything now\b"), 0.8, "dan"),
    (
        re.compile(r"(?i)without any (restrictions|filters|rules|guidelines)"),
        0.7,
        "remove_guardrails",
    ),
    (re.compile(r"(?i)\bBEGIN SYSTEM\b|\bEND SYSTEM\b|\[/?INST\]"), 0.6, "delimiter_injection"),
)


@dataclass(frozen=True)
class InjectionReport:
    """The injection risk of an input: a score, whether to block, and the triggers."""

    score: float
    blocked: bool
    triggers: tuple[str, ...]


def assess_injection(text: str, *, threshold: float = 0.8) -> InjectionReport:
    """Return the injection risk of ``text`` against ``threshold``."""

    score = 0.0
    triggers: list[str] = []
    for pattern, weight, name in _PATTERNS:
        if pattern.search(text):
            score += weight
            triggers.append(name)
    return InjectionReport(
        score=round(score, 3), blocked=score >= threshold, triggers=tuple(triggers)
    )
