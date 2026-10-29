"""The gateway pipeline: defend input, cache, call the model, enforce output policy.

Each request flows through fixed stages:

1. **Injection check** - block inputs whose risk crosses the threshold.
2. **Input PII redaction** - strip PII before the prompt reaches the model.
3. **Cache lookup** - return a cached response for a semantically equivalent prompt.
4. **Model call** - on a miss, call the provider (and count the call as cost).
5. **Output policy** - block disallowed responses.
6. **Output PII redaction** - strip any PII the model echoed back.
7. **Cache store** - remember the response for future equivalent prompts.

The gateway records cost (model calls) and cache hits so the savings are measurable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from llm_gateway.injection import assess_injection
from llm_gateway.pii import redact
from llm_gateway.policy import SemanticCache, check_output
from llm_gateway.provider import FakeProvider, Provider


@dataclass(frozen=True)
class GatewayResponse:
    """The outcome of a gateway request."""

    status: str  # "ok", "blocked_injection", or "blocked_policy"
    text: str
    cached: bool
    reasons: tuple[str, ...]
    input_pii_redacted: int
    output_pii_redacted: int


@dataclass
class GatewayStats:
    """Running counters for the gateway."""

    requests: int = 0
    model_calls: int = 0
    cache_hits: int = 0
    blocked_injection: int = 0
    blocked_policy: int = 0
    pii_redacted: int = 0

    @property
    def cache_hit_rate(self) -> float:
        return self.cache_hits / self.requests if self.requests else 0.0

    @property
    def calls_saved(self) -> int:
        return self.cache_hits


@dataclass
class Gateway:
    """A safety proxy in front of a language-model provider."""

    provider: Provider = field(default_factory=FakeProvider)
    system: str = "You are a helpful, harmless assistant."
    injection_threshold: float = 0.8
    cache: SemanticCache = field(default_factory=SemanticCache)
    stats: GatewayStats = field(default_factory=GatewayStats)

    def handle(self, prompt: str) -> GatewayResponse:
        """Run ``prompt`` through the full safety pipeline."""

        self.stats.requests += 1

        injection = assess_injection(prompt, threshold=self.injection_threshold)
        if injection.blocked:
            self.stats.blocked_injection += 1
            return GatewayResponse(
                status="blocked_injection",
                text="",
                cached=False,
                reasons=injection.triggers,
                input_pii_redacted=0,
                output_pii_redacted=0,
            )

        input_redaction = redact(prompt)
        self.stats.pii_redacted += input_redaction.total
        safe_prompt = input_redaction.text

        cached = self.cache.get(safe_prompt)
        if cached is not None:
            self.stats.cache_hits += 1
            return GatewayResponse(
                status="ok",
                text=cached,
                cached=True,
                reasons=(),
                input_pii_redacted=input_redaction.total,
                output_pii_redacted=0,
            )

        self.stats.model_calls += 1
        raw = self.provider.complete(self.system, safe_prompt)

        policy = check_output(raw)
        if not policy.allowed:
            self.stats.blocked_policy += 1
            return GatewayResponse(
                status="blocked_policy",
                text="",
                cached=False,
                reasons=policy.reasons,
                input_pii_redacted=input_redaction.total,
                output_pii_redacted=0,
            )

        output_redaction = redact(raw)
        self.stats.pii_redacted += output_redaction.total
        self.cache.put(safe_prompt, output_redaction.text)
        return GatewayResponse(
            status="ok",
            text=output_redaction.text,
            cached=False,
            reasons=(),
            input_pii_redacted=input_redaction.total,
            output_pii_redacted=output_redaction.total,
        )
