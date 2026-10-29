# Data Card - LLM Gateway

## Source
- **Authored in-repository.** The adversarial suite is written for this project. There is no external
  dataset, download, or network access in tests or CI.

## Composition
- 14 labeled prompts: injection attempts (generic override, role reassignment, prompt extraction,
  jailbreak, delimiter markers), prompts carrying PII (email, phone, social security number, credit
  card, IP), benign requests, and one combined injection-plus-PII prompt.
- Each prompt is labeled for whether it is an injection attempt and whether it carries PII.

## Labels and supervision
- The labels drive the precision and recall measurements. There is no training.

## Provenance and licensing
- Authored for this repository under the MIT license. The PII values are fictional examples.

## Filtering and contamination
- Not applicable: the suite is a fixed, curated set used only for evaluation.

## Known limitations
- The suite is small and uses well-known attack patterns; it demonstrates the defenses and guards
  against regressions rather than estimating real-world attack coverage.
