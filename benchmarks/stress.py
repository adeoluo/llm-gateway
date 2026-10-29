"""A production-style stress benchmark for the gateway service.

Drives the /complete handler under sustained, concurrent load with a mix of benign
and adversarial prompts and reports throughput with p50, p95, and p99 latency.
Deterministic and offline; run with:

    uv run python benchmarks/stress.py
"""

from __future__ import annotations

import random
import time
from concurrent.futures import ThreadPoolExecutor

from llm_gateway.data import adversarial_suite
from llm_gateway.service import GatewayService, handle


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


def main() -> None:
    service = GatewayService.with_provider()
    rng = random.Random(0)
    prompts = [case.prompt for case in adversarial_suite()]
    requests = [{"prompt": rng.choice(prompts)} for _ in range(10000)]

    def one(body: dict[str, object]) -> float:
        start = time.perf_counter()
        handle("POST", "/complete", body, service)
        return (time.perf_counter() - start) * 1000

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=8) as pool:
        latencies = list(pool.map(one, requests))
    total_s = time.perf_counter() - start

    print(f"Requests: {len(requests)} | Workers: 8")
    print(f"Throughput: {len(requests) / total_s:.0f} req/sec")
    print(
        "Latency ms  "
        f"p50 {_percentile(latencies, 0.50):.3f}  "
        f"p95 {_percentile(latencies, 0.95):.3f}  "
        f"p99 {_percentile(latencies, 0.99):.3f}"
    )


if __name__ == "__main__":
    main()
