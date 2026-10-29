"""A deterministic micro-benchmark for the gateway's defenses.

Reports injection-detection precision and recall, PII-redaction recall, and cache
savings on the adversarial suite. Deterministic and offline; run with:

    uv run python benchmarks/benchmark.py
"""

from __future__ import annotations

import time

from llm_gateway.evaluation import evaluate


def main() -> None:
    start = time.perf_counter()
    report = evaluate()
    elapsed = (time.perf_counter() - start) * 1000
    print(f"Gateway defenses on the adversarial suite ({elapsed:.0f} ms):")
    print(f"  injection precision: {report.injection_precision:.3f}")
    print(f"  injection recall:    {report.injection_recall:.3f}")
    print(f"  PII redaction recall: {report.pii_recall:.3f}")
    print(
        f"  cache hit rate:      {report.cache_hit_rate:.3f} "
        f"({report.model_calls_saved} calls saved)"
    )


if __name__ == "__main__":
    main()
