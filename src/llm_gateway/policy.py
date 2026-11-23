"""Output policy enforcement and a semantic response cache.

The policy blocks model responses that match disallowed content categories (here a
small, clearly fictional deny list) or exceed a length limit. The cache avoids
repeated model calls: it normalizes a prompt and matches it against stored prompts
by token-overlap similarity, so a semantically equivalent prompt reuses a cached
response. Both reduce cost and latency and are reported in the gateway metrics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# A deliberately fictional deny list; real categories would be configured per deployment.
_DISALLOWED = ("forbiddenword", "bannedphrase", "restrictedterm")
_MAX_OUTPUT_CHARS = 8000
_TOKEN_RE = re.compile(r"[a-z0-9']+")
_NEGATIONS = frozenset(
    {
        "no",
        "not",
        "never",
        "none",
        "neither",
        "nor",
        "without",
        "cannot",
        "cant",
        "can't",
        "dont",
        "don't",
        "doesnt",
        "doesn't",
        "isnt",
        "isn't",
        "arent",
        "aren't",
        "wont",
        "won't",
        "shouldnt",
        "shouldn't",
        "unsafe",
    }
)
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "to",
        "of",
        "in",
        "on",
        "for",
        "with",
        "about",
        "it",
        "this",
        "that",
        "please",
        "can",
        "you",
        "what",
        "how",
        "do",
        "does",
    }
)


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


@dataclass(frozen=True)
class _CacheKey:
    all_tokens: frozenset[str]
    content_tokens: frozenset[str]
    negations: frozenset[str]
    numbers: frozenset[str]


def _cache_key(prompt: str) -> _CacheKey:
    words = _TOKEN_RE.findall(prompt.lower())
    all_toks = frozenset(words)
    negs = frozenset(w for w in words if w in _NEGATIONS or w.endswith("n't"))
    nums = frozenset(w for w in words if any(c.isdigit() for c in w))
    content = frozenset(w for w in words if w not in _STOPWORDS and w not in negs)
    return _CacheKey(all_tokens=all_toks, content_tokens=content, negations=negs, numbers=nums)


@dataclass
class SemanticCache:
    """Near-exact lexical response cache with negation, numeric, and content-entity guards.

    Unlike a neural embedding cache, this zero-dependency cache only matches paraphrases that
    share identical negation polarity, identical numeric literals, and high overlap on both
    full tokens and non-stopword content tokens (so ``"is aspirin safe"`` never collides with
    ``"is aspirin not safe"`` or ``"is ibuprofen safe"``).
    """

    threshold: float = 0.85
    _entries: list[tuple[_CacheKey, str]] = field(default_factory=list)
    hits: int = 0
    misses: int = 0

    @staticmethod
    def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
        if not a and not b:
            return 1.0
        union = a | b
        return len(a & b) / len(union) if union else 0.0

    def _matches(self, a: _CacheKey, b: _CacheKey) -> bool:
        if a.negations != b.negations or a.numbers != b.numbers:
            return False
        if self._jaccard(a.content_tokens, b.content_tokens) < max(self.threshold, 0.85):
            return False
        return self._jaccard(a.all_tokens, b.all_tokens) >= self.threshold

    def get(self, prompt: str) -> str | None:
        """Return a cached response for a lexically equivalent prompt, or ``None``."""

        key = _cache_key(prompt)
        for stored, response in self._entries:
            if self._matches(key, stored):
                self.hits += 1
                return response
        self.misses += 1
        return None

    def put(self, prompt: str, response: str) -> None:
        """Store ``response`` for ``prompt``."""

        self._entries.append((_cache_key(prompt), response))

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0
