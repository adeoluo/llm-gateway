"""Output policy enforcement and a semantic response cache.

The policy blocks model responses that match disallowed content categories (here a
small, clearly fictional deny list) or exceed a length limit. The cache avoids
repeated model calls: it normalizes a prompt and matches it against stored prompts
by token-overlap similarity, so a semantically equivalent prompt reuses a cached
response. Both reduce cost and latency and are reported in the gateway metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# A deliberately fictional deny list; real categories would be configured per deployment.
_DISALLOWED = ("forbiddenword", "bannedphrase", "restrictedterm")
_MAX_OUTPUT_CHARS = 8000


@dataclass(frozen=True)
class PolicyReport:
    """Whether a response is allowed and, if not, why."""

    allowed: bool
    reasons: tuple[str, ...]


def check_output(text: str) -> PolicyReport:
    """Return whether ``text`` passes the output policy."""

    reasons: list[str] = []
    lowered = text.lower()
    for term in _DISALLOWED:
        if term in lowered:
            reasons.append(f"disallowed_content:{term}")
    if len(text) > _MAX_OUTPUT_CHARS:
        reasons.append("too_long")
    return PolicyReport(allowed=not reasons, reasons=tuple(reasons))


def _normalize(prompt: str) -> frozenset[str]:
    return frozenset(prompt.lower().split())


@dataclass
class SemanticCache:
    """A small response cache keyed by token-overlap similarity of prompts."""

    threshold: float = 0.8
    _entries: list[tuple[frozenset[str], str]] = field(default_factory=list)
    hits: int = 0
    misses: int = 0

    def _similarity(self, a: frozenset[str], b: frozenset[str]) -> float:
        if not a and not b:
            return 1.0
        union = a | b
        if not union:
            return 0.0
        return len(a & b) / len(union)

    def get(self, prompt: str) -> str | None:
        """Return a cached response for a sufficiently similar prompt, or ``None``."""

        tokens = _normalize(prompt)
        for stored, response in self._entries:
            if self._similarity(tokens, stored) >= self.threshold:
                self.hits += 1
                return response
        self.misses += 1
        return None

    def put(self, prompt: str, response: str) -> None:
        """Store ``response`` for ``prompt``."""

        self._entries.append((_normalize(prompt), response))

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0
