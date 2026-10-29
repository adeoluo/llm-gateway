"""Evaluation: injection-detection quality, PII-redaction recall, cache savings."""

from __future__ import annotations

from dataclasses import dataclass

from llm_gateway.data import SuiteCase, adversarial_suite
from llm_gateway.gateway import Gateway
from llm_gateway.injection import assess_injection
from llm_gateway.pii import contains_pii


@dataclass(frozen=True)
class DefenseReport:
    """Measured quality of the gateway's defenses on the adversarial suite."""

    injection_precision: float
    injection_recall: float
    pii_recall: float
    cache_hit_rate: float
    model_calls_saved: int

    def format(self) -> str:
        return (
            f"injection precision={self.injection_precision:.3f} "
            f"recall={self.injection_recall:.3f}; "
            f"PII redaction recall={self.pii_recall:.3f}; "
            f"cache hit rate={self.cache_hit_rate:.3f} "
            f"({self.model_calls_saved} model calls saved)"
        )


def _injection_scores(cases: list[SuiteCase]) -> tuple[float, float]:
    tp = fp = fn = 0
    for case in cases:
        blocked = assess_injection(case.prompt).blocked
        if case.is_injection and blocked:
            tp += 1
        elif case.is_injection and not blocked:
            fn += 1
        elif not case.is_injection and blocked:
            fp += 1
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return precision, recall


def _pii_recall(cases: list[SuiteCase]) -> float:
    total = caught = 0
    for case in cases:
        if case.has_pii:
            total += 1
            if contains_pii(case.prompt):
                caught += 1
    return caught / total if total else 1.0


def evaluate(cases: list[SuiteCase] | None = None) -> DefenseReport:
    """Score the gateway's defenses and cache savings on the adversarial suite."""

    cases = cases or adversarial_suite()
    precision, recall = _injection_scores(cases)
    pii_recall = _pii_recall(cases)

    # Replay the benign prompts twice to measure cache savings on repeats.
    gateway = Gateway()
    benign = [c.prompt for c in cases if not c.is_injection]
    for prompt in benign + benign:
        gateway.handle(prompt)

    return DefenseReport(
        injection_precision=precision,
        injection_recall=recall,
        pii_recall=pii_recall,
        cache_hit_rate=gateway.stats.cache_hit_rate,
        model_calls_saved=gateway.stats.calls_saved,
    )
