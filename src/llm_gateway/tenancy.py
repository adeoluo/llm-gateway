"""Per-tenant isolation on top of the single-tenant :class:`Gateway`.

A shared gateway must keep tenants apart on three axes:

* **Cache** - each tenant has its own semantic cache, so one tenant can never read a
  response cached for another (even for an identical prompt).
* **Quota** - each tenant has its own token bucket, so one tenant exhausting its rate limit
  cannot deny service to another.
* **Metrics** - counters are recorded per tenant, so usage and cost are attributable.

The whole ``handle`` path is guarded by a lock, so the per-tenant caches, counters, and
rate buckets stay consistent when the gateway is driven from many threads at once. The
model backend is shared (typically a :class:`ResilientProvider`); a provider outage that
survives retry and failover is surfaced as a ``provider_error`` status rather than crashing
the caller.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from llm_gateway.gateway import Gateway, GatewayResponse
from llm_gateway.provider import FakeProvider, Provider
from llm_gateway.rate_limit import Clock, TenantRateLimiter
from llm_gateway.resilience import ProviderError


@dataclass
class TenantMetrics:
    """Per-tenant counters for observability."""

    requests: int = 0
    served: int = 0
    rate_limited: int = 0
    cache_hits: int = 0
    model_calls: int = 0
    blocked_injection: int = 0
    blocked_policy: int = 0
    provider_errors: int = 0

    @property
    def cache_hit_rate(self) -> float:
        return self.cache_hits / self.served if self.served else 0.0


@dataclass(frozen=True)
class TenantResponse:
    """The outcome of a per-tenant request."""

    tenant: str
    status: str  # "ok", "blocked_*", "rate_limited", or "provider_error"
    response: GatewayResponse | None

    @property
    def cached(self) -> bool:
        return self.response is not None and self.response.cached


class MultiTenantGateway:
    """Routes requests to an isolated per-tenant gateway with its own cache and quota."""

    def __init__(
        self,
        *,
        provider: Provider | None = None,
        rate_capacity: float = 1000.0,
        refill_per_second: float = 1000.0,
        clock: Clock = time.monotonic,
        injection_threshold: float = 0.8,
        system: str = "You are a helpful, harmless assistant.",
    ) -> None:
        self._provider = provider or FakeProvider()
        self._injection_threshold = injection_threshold
        self._system = system
        self._rate_limiter = TenantRateLimiter(rate_capacity, refill_per_second, clock)
        self._gateways: dict[str, Gateway] = {}
        self._metrics: dict[str, TenantMetrics] = {}
        self._lock = threading.Lock()

    def _tenant_state(self, tenant: str) -> tuple[Gateway, TenantMetrics]:
        gateway = self._gateways.get(tenant)
        if gateway is None:
            gateway = Gateway(
                provider=self._provider,
                system=self._system,
                injection_threshold=self._injection_threshold,
            )
            self._gateways[tenant] = gateway
            self._metrics[tenant] = TenantMetrics()
        return gateway, self._metrics[tenant]

    def handle(self, tenant: str, prompt: str) -> TenantResponse:
        """Run ``prompt`` through ``tenant``'s isolated gateway, enforcing its quota."""
        with self._lock:
            gateway, metrics = self._tenant_state(tenant)
            metrics.requests += 1

            if not self._rate_limiter.allow(tenant):
                metrics.rate_limited += 1
                return TenantResponse(tenant=tenant, status="rate_limited", response=None)

            calls_before = gateway.stats.model_calls
            try:
                response = gateway.handle(prompt)
            except ProviderError:
                metrics.provider_errors += 1
                return TenantResponse(tenant=tenant, status="provider_error", response=None)

            metrics.served += 1
            if response.cached:
                metrics.cache_hits += 1
            if gateway.stats.model_calls > calls_before:
                metrics.model_calls += 1
            if response.status == "blocked_injection":
                metrics.blocked_injection += 1
            elif response.status == "blocked_policy":
                metrics.blocked_policy += 1
            return TenantResponse(tenant=tenant, status=response.status, response=response)

    def metrics(self, tenant: str) -> TenantMetrics:
        """Return a snapshot copy of ``tenant``'s metrics."""
        with self._lock:
            return TenantMetrics(**vars(self._metrics.get(tenant, TenantMetrics())))

    @property
    def tenants(self) -> list[str]:
        with self._lock:
            return sorted(self._metrics)

    def render_metrics(self) -> str:
        """Render per-tenant counters in the Prometheus text exposition format."""
        with self._lock:
            snapshot = {name: TenantMetrics(**vars(m)) for name, m in self._metrics.items()}
        fields = (
            "requests",
            "served",
            "rate_limited",
            "cache_hits",
            "model_calls",
            "blocked_injection",
            "blocked_policy",
            "provider_errors",
        )
        lines: list[str] = []
        for metric in fields:
            lines.append(f"# HELP tenant_{metric}_total {metric} by tenant.")
            lines.append(f"# TYPE tenant_{metric}_total counter")
            for tenant in sorted(snapshot):
                value = getattr(snapshot[tenant], metric)
                lines.append(f'tenant_{metric}_total{{tenant="{tenant}"}} {value}')
        return "\n".join(lines) + "\n"
