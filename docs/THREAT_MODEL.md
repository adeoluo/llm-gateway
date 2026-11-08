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
- No third-party runtime packages; the production provider uses the standard-library HTTP
  client. Development tooling is pinned via `uv.lock`. CodeQL runs in CI.

## Standards mapping

Each control is mapped to the OWASP Top 10 for LLM Applications 2026 and MITRE ATLAS v2026.10
(IDs and names checked against `ATLAS.yaml` from the
[v2026.10 release of mitre-atlas/atlas-data](https://github.com/mitre-atlas/atlas-data/releases)).
The OWASP Top 10 for Agentic Applications 2026 is not mapped: the gateway fronts single
completions and has no tools, memory or agent identities.

| Threat | OWASP LLM 2026 | MITRE ATLAS v2026.10 | Gateway control |
|---|---|---|---|
| Instruction override, role reassignment and jailbreak markers | LLM01:2026 Prompt Injection | AML.T0051.000 LLM Prompt Injection: Direct; AML.T0054 LLM Jailbreak | Weighted rules block before any model call |
| System prompt extraction | LLM08:2026 Hidden Context Exposure; LLM01:2026 Prompt Injection | AML.T0069.002 Discover LLM System Information: System Prompt | Prompt extraction rules |
| Personal data sent to a third-party model | LLM02:2026 Sensitive Information Disclosure | AML.T0085.002 Data from AI Services: Conversation Context and Memory | Input PII redaction |
| Personal data in responses | LLM02:2026 Sensitive Information Disclosure | AML.T0136 Exfiltration via AI User Interface | Output PII redaction |
| Disallowed or over-long responses | LLM10:2026 Improper Output Handling; LLM06:2026 Unbounded Consumption | AML.T0034.001 Cost Harvesting: Resource-Intensive Queries | Output deny list and length cap |
| One tenant reading another's cached responses | LLM02:2026 Sensitive Information Disclosure; LLM09:2026 Vector and Embedding Weaknesses | AML.T0085.002 Data from AI Services: Conversation Context and Memory | Per-tenant semantic caches |
| Request floods and quota exhaustion | LLM06:2026 Unbounded Consumption | AML.T0034.000 Cost Harvesting: Excessive Queries; AML.T0029 Denial of AI Service | Per-tenant token buckets (AML.M0004 Limit AI Service Query Volume and Rate) |
| Provider API key exposure | LLM02:2026 Sensitive Information Disclosure | AML.T0055 Unsecured Credentials | Key read from the environment, never from requests or logs |
| Malicious dependency | LLM04:2026 Supply Chain | AML.T0010.001 Supply Chain Compromise: Software | No runtime dependencies; CodeQL |

The gateway as a whole is an instance of AML.M0020 Generative AI Guardrails. It does not address
LLM05:2026 Data and Model Poisoning or LLM07:2026 Misinformation. In NIST AI 600-1 (Generative
AI Profile) terms it addresses the Information Security and Data Privacy risks.

## Residual risk
- Rule-based detection cannot catch every attack, and the cache could serve a stale response if the
  underlying policy changes. A deployment would add rate limiting and cache invalidation.
