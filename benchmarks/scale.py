"""A large-workload scale benchmark for the gateway safety pipeline.

Where ``benchmark.py`` reports defense quality on the small adversarial suite and
``stress.py`` drives the HTTP service under concurrent load, this script measures
the core operation - :meth:`Gateway.handle`, which runs a prompt through injection
detection, PII redaction, the semantic cache, the (fake) provider, and output
policy - on progressively larger synthetic request streams. It reports wall-clock
time, throughput, peak memory (via the standard-library :mod:`tracemalloc`),
injection-detection precision and recall, PII-redaction recall, and the cache hit
rate.

The request stream is sampled deterministically from the labeled adversarial
suite (nothing is downloaded), so the run is reproducible, fully offline, and the
model call is the deterministic offline fake provider. Run with:

    uv run python benchmarks/scale.py
"""

from __future__ import annotations

import random
import time
import tracemalloc
from dataclasses import dataclass

from llm_gateway.data import adversarial_suite
from llm_gateway.gateway import Gateway

WORKLOAD_SIZES: tuple[int, ...] = (10_000, 25_000, 50_000, 100_000)


@dataclass(frozen=True, slots=True)
class ScaleRow:
    """One measured row of the scale sweep."""

    size: int
    seconds: float
    throughput: float
    peak_mib: float
    injection_precision: float
    injection_recall: float
    pii_recall: float
    cache_hit_rate: float


def run_workload(size: int, *, seed: int = 0) -> ScaleRow:
    """Push ``size`` synthetic requests through a single gateway.

    Requests are sampled with repetition from the labeled suite, so detection
    precision/recall and PII-redaction recall are measured against known labels
    while the shared cache lets the hit rate build up over the stream.
    """
    cases = adversarial_suite()
    rng = random.Random(seed)
    stream = [cases[rng.randrange(len(cases))] for _ in range(size)]
    gateway = Gateway()

    true_positive = false_positive = false_negative = 0
    pii_total = pii_caught = 0
    tracemalloc.start()
    start = time.perf_counter()
    for case in stream:
        response = gateway.handle(case.prompt)
        blocked = response.status == "blocked_injection"
        if case.is_injection and blocked:
            true_positive += 1
        elif case.is_injection and not blocked:
            false_negative += 1
        elif not case.is_injection and blocked:
            false_positive += 1
        if case.has_pii and not case.is_injection:
            pii_total += 1
            if response.input_pii_redacted > 0:
                pii_caught += 1
    elapsed = time.perf_counter() - start
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    precision = (
        true_positive / (true_positive + false_positive) if true_positive + false_positive else 1.0
    )
    recall = (
        true_positive / (true_positive + false_negative) if true_positive + false_negative else 1.0
    )
    pii_recall = pii_caught / pii_total if pii_total else 1.0
    throughput = size / elapsed if elapsed > 0 else float("inf")
    return ScaleRow(
        size,
        elapsed,
        throughput,
        peak / (1024 * 1024),
        precision,
        recall,
        pii_recall,
        gateway.stats.cache_hit_rate,
    )


def main() -> None:
    print("LLM Gateway scale benchmark")
    print("Data is SYNTHETIC: requests sampled from the labeled adversarial suite.")
    print("The model call uses the deterministic offline fake provider.\n")
    header = (
        f"{'requests':>9}  {'seconds':>8}  {'req/sec':>9}  {'peak MiB':>9}  "
        f"{'inj prec':>9}  {'inj rec':>8}  {'pii rec':>8}  {'cache hit':>10}"
    )
    print(header)
    print("-" * len(header))
    for size in WORKLOAD_SIZES:
        row = run_workload(size)
        print(
            f"{row.size:>9,}  {row.seconds:>8.3f}  {row.throughput:>9,.0f}  "
            f"{row.peak_mib:>9.2f}  {row.injection_precision:>9.3f}  "
            f"{row.injection_recall:>8.3f}  {row.pii_recall:>8.3f}  "
            f"{row.cache_hit_rate:>10.3f}"
        )


if __name__ == "__main__":
    main()
