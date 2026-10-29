# ADR-0002: A single safety pipeline in front of the model

- **Status:** Accepted
- **Date:** 2026-01-01

## Context
A production language-model application needs several safeguards: it must resist prompt injection,
avoid sending personal data to a third party, keep responses within policy, and not pay for repeated
identical calls. Scattering these checks across call sites makes them easy to forget and hard to
audit.

## Decision
Put every request through one gateway pipeline with fixed, ordered stages: injection check, input
PII redaction, semantic cache lookup, model call on a miss, output-policy check, output PII
redaction, and cache store. The gateway exposes counters for cost, cache hits, and blocks.

## Consequences
- The safety boundary is one place to read, test, and change.
- Ordering is explicit: injection is checked before any model call, PII is removed before the prompt
  leaves the process, and policy is enforced before a response is returned.
- A caller cannot accidentally bypass a check, because the model is only reached through the gateway.
