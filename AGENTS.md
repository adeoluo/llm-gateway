# AGENTS.md

Working notes for coding agents and contributors in **LLM Gateway**. The [README](README.md)
explains what the project does and why; this file explains how to change it safely.

## Project

A safety proxy that sits in front of a language-model API: prompt-injection defense, PII redaction, output-policy enforcement, and a semantic response cache. It ships with an adversarial test suite, so its defenses are measured.

## Layout

- `benchmarks/`: benchmark scripts and recorded results
- `docker-compose.yml`: local container setup
- `docs/`: documentation, architecture diagram source and render, design records
- `scripts/`: maintenance scripts (release, assets, data)
- `src/`: library and service source
- `tests/`: test suite

Key modules:

- `src/llm_gateway/__init__.py`: LLM Gateway - a safety proxy for language-model APIs, from scratch.
- `src/llm_gateway/cli.py`: Command line interface for the language-model safety gateway.
- `src/llm_gateway/data.py`: A labeled adversarial suite: injection attempts, PII prompts, and benign inputs.
- `src/llm_gateway/evaluation.py`: Evaluation: injection-detection quality, PII-redaction recall, cache savings.
- `src/llm_gateway/gateway.py`: The gateway pipeline: defend input, cache, call the model, enforce output policy.
- `src/llm_gateway/injection.py`: Prompt-injection detection over user input.
- `src/llm_gateway/observability.py`: In-process request metrics for the HTTP service (Prometheus text exposition).
- `src/llm_gateway/pii.py`: Detection and redaction of personally identifiable information.
- `src/llm_gateway/policy.py`: Output policy enforcement and a semantic response cache.
- `src/llm_gateway/provider.py`: The language-model provider interface, a deterministic fake, and a real client.
- `src/llm_gateway/rate_limit.py`: Per-tenant rate limiting via a token bucket.
- `src/llm_gateway/resilience.py`: Retry-with-backoff and cross-provider failover for the model backend.
- `src/llm_gateway/service.py`: A standard-library HTTP service exposing the safety gateway.
- `src/llm_gateway/tenancy.py`: Per-tenant isolation on top of the single-tenant :class:`Gateway`.

## Commands

| Command | Purpose |
|---|---|
| `make help` | Show this help |
| `make setup` | Install dependencies and pre-commit hooks |
| `make format` | Format automatically |
| `make lint` | Lint (no fixes) |
| `make type` | Type-check |
| `make test` | Run tests |
| `make coverage` | Tests with coverage gate |
| `make evaluation` | Reproduce the results table |
| `make run` | Run the HTTP service |
| `make diagram` | Render architecture diagram to SVG |
| `make docker-build` | Build the image |
| `make docker-up` | Run via docker compose |
| `make clean` | Remove caches and artifacts |
| `make all` | Full local gate (mirror of continuous integration) |
| `make go-test` | Go proxy: gofmt check, vet, race tests |
| `make go-parity` | Regenerate the Go parity fixtures from the Python rules |
| `make changelog` | Regenerate CHANGELOG.md from Conventional Commits (git-cliff) |
| `make cut-release` | Cut a release locally: version bump, changelog, tag, GitHub release (RELEASE_VERSION=vX.Y.Z optional) |

Run the full local gate (`make all`) before committing; CI runs the same checks.

## Conventions

- Commits follow Conventional Commits (`feat:`, `fix:`, `perf:`, `refactor:`, `docs:`, `test:`, `ci:`, `chore:`).
  The changelog and the next version number are derived from them.
- Every number quoted in the README is produced by a command in this repository. When behavior
  changes, rerun that command and update the number in the same commit.
- When a component is added, removed or renamed, update `docs/architecture/architecture.mmd`
  and re-render `architecture.svg` so the diagram matches the code.
- README sections keep their fixed order. Prose avoids em and en dashes and promotional wording.
- Tests accompany behavior changes; a bug fix comes with a test that fails without it.
- Releases are cut by the maintainer with `make cut-release`, never from CI.

## Python notes

- Python is managed with `uv`; run commands through `uv run` so the locked environment is used.
- Lint and format with `ruff`; type-check with `mypy`; tests use `pytest`.
- Public functions carry type hints and a docstring that states the contract, not the steps.
