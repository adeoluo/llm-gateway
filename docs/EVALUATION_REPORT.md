# Evaluation Report - LLM Gateway

> Reproduce with `python -m llm_gateway report` and `benchmarks/benchmark.py`. The adversarial suite
> and the offline provider are deterministic.

## Setup & Scope

- **Regression fixture (`src/llm_gateway/data.py` + `go/gateway/testdata/parity.json`):** 14
  end-to-end pipeline regression prompts plus a 28-case Python-to-Go parity fixture verifying exact
  cross-language agreement on NFKC/whitespace/zero-width-normalized injection rules and
  Luhn-validated structured PII redaction (`CREDIT_CARD`, `SSN`, `EMAIL`, `PHONE`, `IP`, `DOB`,
  `PASSPORT`, `API_KEY`). This fixture is a deterministic rule regression check, not an open-world
  ML benchmark (for 91k-prompt ML injection evaluation, see `prompt-injection-detector`, which
  plugs into `Gateway(injection_classifier=...)`). Free-form person names require NER and are out
  of scope for the zero-dependency regex stage.
- **Provider:** the offline provider, so results are reproducible with no credentials.
- **Metrics:** rule precision and recall on the regression fixture, structured PII redaction
  recall, and polarity/entity-guarded lexical cache hit rate on repeated prompts.
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
