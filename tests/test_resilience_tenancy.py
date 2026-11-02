"""Tests for retry-with-backoff, cross-provider failover, tenant isolation, and
thread-safety of the multi-tenant gateway.

Every test uses the deterministic offline providers (:class:`FakeProvider`,
:class:`FlakyProvider`, :class:`FailingProvider`), so reliability and isolation are proven
with no network access. In production the backend is a real model behind the same
:class:`Provider` interface.
"""

from __future__ import annotations

import threading

import pytest

from llm_gateway.gateway import Gateway
from llm_gateway.provider import FakeProvider
from llm_gateway.rate_limit import TenantRateLimiter, TokenBucket
from llm_gateway.resilience import (
    FailingProvider,
    FlakyProvider,
    ProviderError,
    ResilientProvider,
)
from llm_gateway.tenancy import MultiTenantGateway


# --------------------------------------------------------------------------------------
# Retry with backoff
# --------------------------------------------------------------------------------------
def test_retry_recovers_after_transient_failures() -> None:
    delays: list[float] = []
    flaky = FlakyProvider(fail_times=2, name="primary")
    provider = ResilientProvider([flaky], max_attempts=3, sleep=delays.append)

    result = provider.complete("sys", "a benign question")

    assert result.startswith("A concise, safe answer")
    assert provider.stats.attempts == 3  # two failures + one success
    assert provider.stats.retries == 2
    assert provider.stats.failovers == 0
    assert provider.stats.successes == 1
    # Exponential backoff was applied before each retry (0.05, then 0.10).
    assert delays == [pytest.approx(0.05), pytest.approx(0.10)]
    assert provider.stats.recovery_rate == 1.0


def test_retry_gives_up_after_max_attempts_on_single_provider() -> None:
    provider = ResilientProvider([FailingProvider()], max_attempts=3)
    with pytest.raises(ProviderError):
        provider.complete("sys", "q")
    assert provider.stats.attempts == 3
    assert provider.stats.exhausted == 1
    assert provider.stats.recovery_rate == 0.0


# --------------------------------------------------------------------------------------
# Failover across providers
# --------------------------------------------------------------------------------------
def test_failover_picks_next_provider_when_primary_is_down() -> None:
    primary = FailingProvider(name="primary")
    fallback = FlakyProvider(fail_times=0, name="fallback")
    provider = ResilientProvider([primary, fallback], max_attempts=2)

    result = provider.complete("sys", "summarize the report")

    assert result.startswith("A concise, safe answer")
    assert primary.calls == 2  # primary exhausted its attempts
    assert fallback.calls == 1  # fallback served the request
    assert provider.stats.failovers == 1
    assert provider.stats.successes == 1


def test_failover_exhausts_all_providers() -> None:
    provider = ResilientProvider(
        [FailingProvider(name="a"), FailingProvider(name="b")], max_attempts=1
    )
    with pytest.raises(ProviderError, match="all 2 providers failed"):
        provider.complete("sys", "q")
    assert provider.stats.failovers == 1
    assert provider.stats.exhausted == 1


def test_resilient_provider_validates_construction() -> None:
    with pytest.raises(ValueError, match="at least one provider"):
        ResilientProvider([])
    with pytest.raises(ValueError, match="max_attempts"):
        ResilientProvider([FakeProvider()], max_attempts=0)


def test_gateway_uses_resilient_provider_transparently() -> None:
    # The gateway sees a healthy provider even though the primary fails twice first.
    flaky = FlakyProvider(fail_times=2)
    gateway = Gateway(provider=ResilientProvider([flaky], max_attempts=3))
    response = gateway.handle("what is a good soup recipe for dinner")
    assert response.status == "ok"
    assert response.text.startswith("A concise, safe answer")


# --------------------------------------------------------------------------------------
# Token bucket + per-tenant rate limiter
# --------------------------------------------------------------------------------------
def test_token_bucket_refills_over_time() -> None:
    bucket = TokenBucket(capacity=2, refill_per_second=1.0)
    assert bucket.allow(now=0.0)
    assert bucket.allow(now=0.0)
    assert not bucket.allow(now=0.0)  # empty
    assert bucket.allow(now=1.0)  # one token refilled after a second


def test_rate_limiter_isolates_tenants() -> None:
    limiter = TenantRateLimiter(capacity=2, refill_per_second=0.0, clock=lambda: 0.0)
    assert limiter.allow("tenant-a")
    assert limiter.allow("tenant-a")
    assert not limiter.allow("tenant-a")  # tenant-a is exhausted
    # tenant-b is completely unaffected by tenant-a draining its bucket.
    assert limiter.allow("tenant-b")
    assert limiter.remaining("tenant-b") == 1.0


# --------------------------------------------------------------------------------------
# Multi-tenant gateway: quota isolation
# --------------------------------------------------------------------------------------
def test_one_tenant_cannot_exhaust_anothers_quota() -> None:
    gateway = MultiTenantGateway(rate_capacity=2, refill_per_second=0.0, clock=lambda: 0.0)

    first = gateway.handle("alice", "a question about the weather")
    second = gateway.handle("alice", "another question about lunch")
    third = gateway.handle("alice", "a third question about travel")

    assert first.status == "ok"
    assert second.status == "ok"
    assert third.status == "rate_limited"  # alice is out of quota

    # bob still has his full quota despite alice being throttled.
    bob = gateway.handle("bob", "a question about the weather")
    assert bob.status == "ok"
    assert gateway.metrics("alice").rate_limited == 1
    assert gateway.metrics("bob").rate_limited == 0


# --------------------------------------------------------------------------------------
# Multi-tenant gateway: cache isolation
# --------------------------------------------------------------------------------------
class _CountingProvider:
    """Returns a distinct answer per call, so a shared cache would be observable."""

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, system: str, prompt: str) -> str:
        self.calls += 1
        return f"answer-{self.calls}"


def test_one_tenant_cannot_read_anothers_cache() -> None:
    provider = _CountingProvider()
    gateway = MultiTenantGateway(provider=provider)
    prompt = "what is the status of my recent order please"

    alice_first = gateway.handle("alice", prompt)
    alice_second = gateway.handle("alice", prompt)
    bob_first = gateway.handle("bob", prompt)

    # Alice's repeat is served from her own cache (no new model call).
    assert alice_first.cached is False
    assert alice_second.cached is True
    assert alice_second.response is not None
    assert alice_second.response.text == alice_first.response.text  # type: ignore[union-attr]

    # Bob's identical prompt does NOT read Alice's cache: it is a fresh model call with a
    # different answer, proving the caches are isolated.
    assert bob_first.cached is False
    assert bob_first.response is not None
    assert bob_first.response.text != alice_first.response.text  # type: ignore[union-attr]
    assert gateway.metrics("alice").cache_hits == 1
    assert gateway.metrics("bob").cache_hits == 0


# --------------------------------------------------------------------------------------
# Multi-tenant gateway: provider outage surfaced, not crashing
# --------------------------------------------------------------------------------------
def test_provider_outage_surfaces_as_status() -> None:
    gateway = MultiTenantGateway(provider=ResilientProvider([FailingProvider()], max_attempts=1))
    outcome = gateway.handle("alice", "a benign question about the weather")
    assert outcome.status == "provider_error"
    assert outcome.response is None
    assert gateway.metrics("alice").provider_errors == 1


# --------------------------------------------------------------------------------------
# Observability: per-tenant metrics render
# --------------------------------------------------------------------------------------
def test_render_metrics_is_prometheus_text() -> None:
    gateway = MultiTenantGateway()
    gateway.handle("alice", "a benign question about the weather today")
    gateway.handle("bob", "a benign question about lunch options")
    rendered = gateway.render_metrics()
    assert 'tenant_requests_total{tenant="alice"} 1' in rendered
    assert 'tenant_requests_total{tenant="bob"} 1' in rendered
    assert "# TYPE tenant_served_total counter" in rendered


def test_tenant_metrics_helpers_and_defaults() -> None:
    gateway = MultiTenantGateway(provider=_CountingProvider())
    prompt = "please summarize the quarterly report in two bullets"
    gateway.handle("alice", prompt)
    gateway.handle("alice", prompt)  # a cache hit
    assert gateway.tenants == ["alice"]
    assert gateway.metrics("alice").cache_hit_rate == 0.5
    # An unknown tenant yields a fresh, empty snapshot without creating state.
    assert gateway.metrics("ghost").requests == 0
    assert gateway.tenants == ["alice"]


def test_token_bucket_and_limiter_validation() -> None:
    with pytest.raises(ValueError, match="capacity"):
        TokenBucket(capacity=0, refill_per_second=1.0)
    with pytest.raises(ValueError, match="refill_per_second"):
        TokenBucket(capacity=1, refill_per_second=-1.0)


# --------------------------------------------------------------------------------------
# Concurrency: thread-safety of per-tenant counters and caches
# --------------------------------------------------------------------------------------
def test_concurrent_requests_keep_counters_and_caches_consistent() -> None:
    gateway = MultiTenantGateway()
    tenants = ("alice", "bob", "carol")
    per_tenant_requests = 200
    barrier = threading.Barrier(len(tenants))

    def drive(tenant: str) -> None:
        barrier.wait()
        for index in range(per_tenant_requests):
            # A small set of repeated prompts, so the cache is exercised concurrently.
            gateway.handle(tenant, f"question number {index % 5} about the daily report")

    threads = [threading.Thread(target=drive, args=(tenant,)) for tenant in tenants]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    for tenant in tenants:
        metrics = gateway.metrics(tenant)
        # No lost updates: every request is accounted for exactly once.
        assert metrics.requests == per_tenant_requests
        assert metrics.served == per_tenant_requests
        # Five distinct prompts means five model calls; the rest are cache hits.
        assert metrics.model_calls == 5
        assert metrics.cache_hits == per_tenant_requests - 5
