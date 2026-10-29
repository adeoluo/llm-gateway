# ADR-0003: Layered, weighted injection detection

- **Status:** Accepted
- **Date:** 2026-01-01

## Context
Prompt injection has no single reliable signature. A detector built on one phrase is both easy to
evade and prone to false positives. The gateway needs a detector that is tunable and whose
precision-recall trade-off is explicit.

## Decision
Score an input as a weighted sum over a set of high-signal patterns (instruction override, role
reassignment, prompt extraction, jailbreak personas, delimiter markers). Block when the score crosses
a configurable threshold. Strong single patterns carry enough weight to block alone; weak patterns
only contribute.

## Consequences
- The threshold sets the operating point: on the adversarial suite the default reaches precision 1.0
  and recall 0.857, and lowering it trades precision for more recall.
- Adding a new attack pattern is a one-line change with a weight, and its effect on the suite is
  measured immediately.
- The detector is a strong first layer, not a guarantee; the documentation says so plainly.
