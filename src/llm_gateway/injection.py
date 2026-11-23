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
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

InjectionScorer = Callable[[str], float]

_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\u2060\ufeff\u00ad\U000e0000-\U000e007f]+")
_WS_RE = re.compile(r"\s+")

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
    (
        re.compile(
            r"(?i)\bBEGIN SYSTEM\b|\bEND SYSTEM\b|\[/?INST\]|<\|im_start\|>\s*system|<IMPORTANT>"
        ),
        0.6,
        "delimiter_injection",
    ),
)


def _normalize_text(text: str) -> str:
    """Fold compatibility characters, strip zero-width/tag chars, and collapse whitespace."""
    folded = unicodedata.normalize("NFKC", text)
    stripped = _ZERO_WIDTH_RE.sub("", folded)
    return _WS_RE.sub(" ", stripped).strip()


@dataclass(frozen=True)
class InjectionReport:
    """The injection risk of an input: a score, whether to block, and the triggers."""

    score: float
    blocked: bool
    triggers: tuple[str, ...]


def assess_injection(
    text: str,
    *,
    threshold: float = 0.8,
    classifier: InjectionScorer | None = None,
) -> InjectionReport:
    """Return the injection risk of ``text`` against ``threshold``.

    When ``classifier`` is provided (for example ``prompt_injection_detector.score``),
    its probability score is fused with the rule score (`max(rule_score, ml_score)`),
    adding ``"ml_classifier"`` to ``triggers`` when the model crosses ``threshold``.
    """

    normalized = _normalize_text(text)
    score = 0.0
    triggers: list[str] = []
    for pattern, weight, name in _PATTERNS:
        if pattern.search(normalized):
            score += weight
            triggers.append(name)
    if classifier is not None:
        ml_score = float(classifier(text))
        if ml_score >= threshold:
            triggers.append("ml_classifier")
        score = max(score, ml_score)
    return InjectionReport(
        score=round(score, 3), blocked=score >= threshold, triggers=tuple(triggers)
    )
