# Model / System Card - LLM Gateway

## Overview
- **What it is:** a safety proxy in front of a language-model API, combining prompt-injection
  defense, PII redaction, output-policy enforcement, and a semantic cache. No third-party
  dependency.
- **Base model:** pluggable. Offline, a deterministic provider is used for tests and CI; in
  production, Anthropic's Claude via the Messages API.
- **Version and date:** 0.1.0, 2026.

## Intended use
- **Primary use case:** enforcing a safety and cost boundary in front of a production language model.
- **Primary users:** teams deploying language-model features who need a central guard.

## Out-of-scope / prohibited use
- Not a complete security solution; rule-based injection detection cannot catch every attack.
- Not a substitute for the model provider's own safety systems; it complements them.

## Performance
- Injection precision 1.000 and recall 0.857, PII redaction recall 1.000 on the adversarial suite.
- Full method and tables: [`EVALUATION_REPORT.md`](EVALUATION_REPORT.md).

## Limitations and failure modes
- Novel injection phrasings may evade the rules; the threshold trades precision for recall.
- Regex PII detection misses unusual formats and names.
- Token-overlap caching treats low-overlap paraphrases as distinct.

## Ethical considerations
- The gateway reduces the chance of sending PII to a third party, but callers remain responsible for
  what they submit. Credentials are read from the environment and never logged.
