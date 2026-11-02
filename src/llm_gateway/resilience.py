"""Retry-with-backoff and cross-provider failover for the model backend.

A production gateway cannot assume the upstream model always answers on the first try.
Two failure modes are handled here, both behind the same :class:`Provider` protocol the
rest of the gateway already depends on, so nothing downstream changes:

* **Transient failures** - a provider that occasionally raises :class:`ProviderError` is
  retried a bounded number of times with exponential backoff.
* **Provider outage** - when a provider is exhausted, the request *fails over* to the next
  provider in an ordered list, so a healthy fallback serves the request.

Everything is deterministic and offline. :class:`FlakyProvider` fails a fixed number of
times and then succeeds, and :class:`FailingProvider` always fails, so recovery and
failover can be proven in tests without touching a network. The backoff ``sleep`` function
is injectable, so tests observe the schedule without actually waiting.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from llm_gateway.provider import FakeProvider, Provider

Sleeper = Callable[[float], None]


class ProviderError(RuntimeError):
    """A recoverable failure from a model provider (transient or an outage)."""


@dataclass
class FlakyProvider:
    """A provider that raises ``ProviderError`` its first ``fail_times`` calls, then succeeds.

    This models an upstream that is briefly unhealthy and then recovers, letting the retry
    logic be proven deterministically: the N transient failures are followed by a success.
    """

    fail_times: int
    delegate: Provider = field(default_factory=FakeProvider)
    name: str = "flaky"
    calls: int = 0

    def complete(self, system: str, prompt: str) -> str:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ProviderError(f"{self.name}: transient failure {self.calls}/{self.fail_times}")
        return self.delegate.complete(system, prompt)


@dataclass
class FailingProvider:
    """A provider that always raises ``ProviderError`` - a stand-in for a total outage."""

    name: str = "failing"
    calls: int = 0

    def complete(self, system: str, prompt: str) -> str:
        self.calls += 1
        raise ProviderError(f"{self.name}: provider unavailable")


@dataclass
class RetryStats:
    """Counters describing retry and failover activity, for observability."""

    attempts: int = 0  # total provider.complete calls made
    retries: int = 0  # retries after a transient failure on the same provider
    failovers: int = 0  # times the request moved on to the next provider
    successes: int = 0  # requests that eventually succeeded
    exhausted: int = 0  # requests that failed after every provider was tried

    @property
    def recovery_rate(self) -> float:
        """Share of handled requests that ultimately succeeded."""
        total = self.successes + self.exhausted
        return self.successes / total if total else 1.0


@dataclass
class ResilientProvider:
    """Wraps an ordered list of providers with bounded retry and failover.

    For each provider in order, the request is attempted up to ``max_attempts`` times,
    sleeping ``backoff_base * backoff_factor**(attempt-1)`` seconds (capped at
    ``max_backoff``) between tries. If a provider is exhausted, the request fails over to
    the next one. Only :class:`ProviderError` is treated as retryable; any other exception
    is a programming error and propagates unchanged.
    """

    providers: list[Provider]
    max_attempts: int = 3
    backoff_base: float = 0.05
    backoff_factor: float = 2.0
    max_backoff: float = 1.0
    sleep: Sleeper = field(default=lambda _seconds: None)
    stats: RetryStats = field(default_factory=RetryStats)

    def __post_init__(self) -> None:
        if not self.providers:
            raise ValueError("ResilientProvider needs at least one provider")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")

    def backoff_for(self, attempt: int) -> float:
        """Return the (deterministic) backoff delay before retry ``attempt`` (1-based)."""
        return min(self.max_backoff, self.backoff_base * self.backoff_factor ** (attempt - 1))

    def complete(self, system: str, prompt: str) -> str:
        last_error: ProviderError | None = None
        for provider_index, provider in enumerate(self.providers):
            if provider_index > 0:
                self.stats.failovers += 1
            for attempt in range(1, self.max_attempts + 1):
                self.stats.attempts += 1
                try:
                    result = provider.complete(system, prompt)
                except ProviderError as error:
                    last_error = error
                    if attempt < self.max_attempts:
                        self.stats.retries += 1
                        self.sleep(self.backoff_for(attempt))
                    continue
                self.stats.successes += 1
                return result
        self.stats.exhausted += 1
        raise ProviderError(f"all {len(self.providers)} providers failed; last error: {last_error}")
