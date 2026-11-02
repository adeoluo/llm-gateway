"""Per-tenant rate limiting via a token bucket.

Multi-tenant gateways must stop one tenant's traffic from starving another's. Each tenant
gets an independent token bucket: a bucket holds up to ``capacity`` tokens and refills at
``refill_per_second``; a request costs one token and is rejected when the bucket is empty.
Because the buckets are keyed by tenant, exhausting one tenant's bucket has no effect on
any other tenant's.

The clock is injectable, so tests pin time (and therefore refill) and prove isolation
deterministically; production uses :func:`time.monotonic`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

Clock = Callable[[], float]


@dataclass
class TokenBucket:
    """A single refilling token bucket."""

    capacity: float
    refill_per_second: float
    tokens: float = field(init=False)
    last_refill: float = 0.0

    def __post_init__(self) -> None:
        if self.capacity <= 0:
            raise ValueError("capacity must be positive")
        if self.refill_per_second < 0:
            raise ValueError("refill_per_second must be non-negative")
        self.tokens = self.capacity

    def allow(self, now: float, cost: float = 1.0) -> bool:
        """Refill for elapsed time and consume ``cost`` tokens if available."""
        elapsed = max(0.0, now - self.last_refill)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_second)
        self.last_refill = now
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False


@dataclass
class TenantRateLimiter:
    """An independent token bucket per tenant, created on first use."""

    capacity: float
    refill_per_second: float
    clock: Clock = time.monotonic
    _buckets: dict[str, TokenBucket] = field(default_factory=dict)

    def allow(self, tenant: str, cost: float = 1.0) -> bool:
        """Return whether ``tenant`` may make a request now, consuming quota if so."""
        bucket = self._buckets.get(tenant)
        if bucket is None:
            bucket = TokenBucket(self.capacity, self.refill_per_second, last_refill=self.clock())
            self._buckets[tenant] = bucket
        return bucket.allow(self.clock(), cost)

    def remaining(self, tenant: str) -> float:
        """Return the tokens currently available to ``tenant`` (for observability)."""
        bucket = self._buckets.get(tenant)
        return bucket.tokens if bucket is not None else self.capacity
