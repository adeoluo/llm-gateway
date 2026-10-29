# Evaluation Report - LLM Gateway

> Reproduce with `python -m llm_gateway report` and `benchmarks/benchmark.py`. The adversarial suite
> and the offline provider are deterministic.

## Setup

- **Adversarial suite:** 14 prompts, each labeled as an injection attempt and as carrying PII.
  Injection strings are generic, well-known patterns; PII prompts carry emails, phone numbers, a
  social security number, a credit card, and an IP address; benign prompts are ordinary requests.
- **Provider:** the offline provider, so results are reproducible with no credentials.
- **Metrics:** injection precision and recall, PII-redaction recall, and the semantic cache hit rate
  on repeated prompts.
- **Hardware / cost:** CPU only; a report runs in a few milliseconds. No external services.

## Results

| Defense | Value |
|---|---:|
| injection detection precision | 1.000 |
| injection detection recall | 0.857 |
| PII redaction recall | 1.000 |
| semantic cache hit rate on repeats | 0.500 |
| model calls saved by the cache | 7 |

The gateway blocks injection at precision 1.0 (no benign prompt is blocked) and recall 0.857 (six of
seven attacks), redacts all PII in the suite, and the cache serves half of repeated prompts, saving
those model calls. The single missed injection is a bare delimiter marker scored below the block
threshold; lowering the threshold catches it at some cost to precision.

## Pipeline behavior

- An injection-flagged prompt is blocked before any model call; the cost counter stays at zero for it.
- Input PII is redacted to typed placeholders before the prompt reaches the model.
- A disallowed or over-long model response is blocked by the output policy.
- Output PII is redacted from the model's response before it is returned and cached.

## Service performance

The `/complete` handler runs the full pipeline. With the offline provider a concurrent stress
benchmark sustains about 8,400 requests per second with p50 near 0.07 ms. In production the latency
is dominated by the model call, which the cache avoids on repeats.

## Reproducibility

- Deterministic: the suite and offline provider produce identical results every run.
- No network access, no credentials, no external data in CI.
- Regenerate every number with the CLI and `benchmarks/benchmark.py`.
