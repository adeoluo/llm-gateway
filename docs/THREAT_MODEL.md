# Threat Model - LLM Gateway

## Assets
- The HTTP service's availability and the integrity of its responses, downstream systems protected by
  the gateway, and any credentials used by a production provider.

## Trust boundaries
- The user input is untrusted. The gateway is the trust boundary in front of the model. In
  production the (redacted) prompt is sent to a third-party model over HTTPS.

## Entry points and mitigations

### `POST /complete`
- **Malformed JSON** is rejected with 400 before routing.
- **Validation:** the prompt must be a non-empty string within a size bound.
- **Injection defense:** inputs whose weighted risk crosses the threshold are blocked before any
  model call.
- **PII redaction:** personal data is removed from the prompt before it leaves the process and from
  the response before it is returned.
- **Output policy:** disallowed or over-long responses are blocked.

### `POST /inspect`
- Assesses a prompt for injection and PII without calling the model, so it is safe and cheap.

### `GET` routes
- `/health`, `/ready`, `/report`, `/stats`, and `/metrics` take no user input and return fixed-shape
  payloads. `/metrics` exposes only aggregate counters.

## Provider and credentials
- The offline provider needs no secrets. The Anthropic provider reads its key from the environment,
  never from the request, and never logs it. CI uses only the offline provider.

## Supply chain
- Zero third-party runtime dependencies; the production provider uses the standard-library HTTP
  client. Development tooling is pinned via `uv.lock`. CodeQL and dependency scanning run in CI.

## Residual risk
- Rule-based detection cannot catch every attack, and the cache could serve a stale response if the
  underlying policy changes. A deployment would add rate limiting and cache invalidation.
