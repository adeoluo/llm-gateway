"""A reliability and tenant-isolation benchmark for the gateway.

Where ``scale.py`` measures the core pipeline under volume, this script measures the
*reliability* layer added on top of it, all with the deterministic offline providers:

1. **Retry + failover** - a primary provider that fails a fixed number of times per request
   (transient) backed by a healthy fallback. It reports the recovery rate (share of
   requests that ultimately succeed) and the retry/failover counts.
2. **Per-tenant cache isolation** - several tenants replay a shared prompt stream through a
   :class:`MultiTenantGateway`. It reports each tenant's independent cache hit rate,
   confirming that caches do not leak across tenants.

Nothing is downloaded and the model call is the offline fake provider, so the run is fully
reproducible. In production the backend is a real model behind the same ``Provider``
interface; these numbers measure the reliability machinery, not a model's quality.

    uv run python benchmarks/reliability.py
"""

from __future__ import annotations

import random

from llm_gateway.provider import FakeProvider
from llm_gateway.resilience import (
    FailingProvider,
    FlakyProvider,
    ProviderError,
    ResilientProvider,
)
from llm_gateway.tenancy import MultiTenantGateway

_PROMPTS: tuple[str, ...] = (
    "summarize the quarterly report in three bullet points",
    "what is a good recipe for a vegetable soup",
    "translate the following sentence into french",
    "draft a polite reply to a customer complaint",
    "explain the status of my recent order",
)


def recovery_sweep(requests: int = 2000, *, fail_times: int = 2, seed: int = 0) -> None:
    """Drive many requests through a flaky primary with a healthy fallback."""
    rng = random.Random(seed)
    print(f"Retry + failover over {requests} requests (primary fails {fail_times}x each):")
    # Each request gets a freshly flaky primary so the transient failures recur, proving
    # recovery is not a one-time warm-up effect.
    successes = 0
    stats_attempts = stats_retries = stats_failovers = 0
    for _ in range(requests):
        provider = ResilientProvider(
            [FlakyProvider(fail_times=fail_times, name="primary"), FakeProvider()],
            max_attempts=fail_times + 1,
        )
        prompt = _PROMPTS[rng.randrange(len(_PROMPTS))]
        try:
            provider.complete("sys", prompt)
            successes += 1
        except ProviderError:
            pass
        stats_attempts += provider.stats.attempts
        stats_retries += provider.stats.retries
        stats_failovers += provider.stats.failovers
    rate = successes / requests
    print(f"  recovery rate     : {rate:.3f} ({successes}/{requests})")
    print(f"  total attempts    : {stats_attempts}")
    print(f"  total retries     : {stats_retries}")
    print(f"  total failovers   : {stats_failovers}")
    print()


def failover_sweep(requests: int = 2000, *, seed: int = 1) -> None:
    """Drive requests where the primary is fully down, forcing failover every time."""
    rng = random.Random(seed)
    provider = ResilientProvider([FailingProvider(name="primary"), FakeProvider()], max_attempts=2)
    successes = 0
    for _ in range(requests):
        provider.complete("sys", _PROMPTS[rng.randrange(len(_PROMPTS))])
        successes += 1
    print(f"Failover with a dead primary over {requests} requests:")
    print(f"  recovery rate     : {successes / requests:.3f}")
    print(f"  failovers         : {provider.stats.failovers}")
    print(f"  successes         : {provider.stats.successes}")
    print()


def tenant_cache_sweep(tenants: int = 4, requests_per_tenant: int = 1000, *, seed: int = 2) -> None:
    """Replay a shared prompt stream through several isolated tenants."""
    rng = random.Random(seed)
    gateway = MultiTenantGateway()
    stream = [_PROMPTS[rng.randrange(len(_PROMPTS))] for _ in range(requests_per_tenant)]
    for index in range(tenants):
        tenant = f"tenant-{index}"
        for prompt in stream:
            gateway.handle(tenant, prompt)
    print(f"Per-tenant cache isolation ({tenants} tenants, {requests_per_tenant} requests each):")
    for tenant in gateway.tenants:
        metrics = gateway.metrics(tenant)
        print(
            f"  {tenant}: hit rate {metrics.cache_hit_rate:.3f}, "
            f"model calls {metrics.model_calls}, cache hits {metrics.cache_hits}"
        )
    print()


def main() -> None:
    recovery_sweep()
    failover_sweep()
    tenant_cache_sweep()


if __name__ == "__main__":
    main()
