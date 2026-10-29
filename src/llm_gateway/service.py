"""A dependency-free HTTP service exposing the safety gateway.

The service wraps a gateway over the offline provider by default, so it runs with
no credentials; a real provider can be injected in production. The routing logic
is a pure function tested without a socket.

Endpoints
---------
``GET  /health``   liveness and the active provider name.
``GET  /ready``    readiness.
``GET  /metrics``  per-route request, error, and latency metrics (Prometheus text).
``POST /complete`` body ``{"prompt": str}``; a guarded completion with safety status.
``POST /inspect``  body ``{"prompt": str}``; injection and PII assessment without a model call.
``GET  /report``   defense quality and cache savings on the adversarial suite.
``GET  /stats``    running gateway counters.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from llm_gateway.evaluation import evaluate
from llm_gateway.gateway import Gateway
from llm_gateway.injection import assess_injection
from llm_gateway.observability import ServiceMetrics
from llm_gateway.pii import redact
from llm_gateway.provider import FakeProvider, Provider

JsonObject = dict[str, Any]
_MAX_PROMPT = 20000


@dataclass(frozen=True)
class GatewayService:
    """Holds a gateway and answers completion, inspection, and report requests."""

    gateway: Gateway
    provider_name: str
    metrics: ServiceMetrics = field(default_factory=ServiceMetrics)

    @classmethod
    def with_provider(cls, provider: Provider | None = None) -> GatewayService:
        provider = provider or FakeProvider()
        return cls(gateway=Gateway(provider=provider), provider_name=type(provider).__name__)

    def complete(self, prompt: str) -> JsonObject:
        response = self.gateway.handle(prompt)
        return {
            "status": response.status,
            "text": response.text,
            "cached": response.cached,
            "reasons": list(response.reasons),
            "input_pii_redacted": response.input_pii_redacted,
            "output_pii_redacted": response.output_pii_redacted,
        }

    def inspect(self, prompt: str) -> JsonObject:
        injection = assess_injection(prompt, threshold=self.gateway.injection_threshold)
        redaction = redact(prompt)
        return {
            "injection_score": injection.score,
            "injection_blocked": injection.blocked,
            "injection_triggers": list(injection.triggers),
            "pii_counts": redaction.counts,
            "redacted_prompt": redaction.text,
        }

    def report(self) -> JsonObject:
        report = evaluate()
        return {
            "injection_precision": round(report.injection_precision, 6),
            "injection_recall": round(report.injection_recall, 6),
            "pii_recall": round(report.pii_recall, 6),
            "cache_hit_rate": round(report.cache_hit_rate, 6),
            "model_calls_saved": report.model_calls_saved,
        }

    def stats(self) -> JsonObject:
        stats = self.gateway.stats
        return {
            "requests": stats.requests,
            "model_calls": stats.model_calls,
            "cache_hits": stats.cache_hits,
            "blocked_injection": stats.blocked_injection,
            "blocked_policy": stats.blocked_policy,
            "pii_redacted": stats.pii_redacted,
            "cache_hit_rate": round(stats.cache_hit_rate, 6),
        }


def _valid_prompt(value: Any) -> str | None:
    if not isinstance(value, str) or not value or len(value) > _MAX_PROMPT:
        return None
    return value


def _route(
    method: str, path: str, body: Mapping[str, Any], service: GatewayService
) -> tuple[int, JsonObject]:
    if method == "GET" and path == "/health":
        return 200, {"status": "ok", "provider": service.provider_name}
    if method == "GET" and path == "/report":
        return 200, service.report()
    if method == "GET" and path == "/stats":
        return 200, service.stats()
    if method == "POST" and path == "/complete":
        prompt = _valid_prompt(body.get("prompt"))
        if prompt is None:
            return 400, {
                "error": f"'prompt' must be a non-empty string of at most {_MAX_PROMPT} characters"
            }
        return 200, service.complete(prompt)
    if method == "POST" and path == "/inspect":
        prompt = _valid_prompt(body.get("prompt"))
        if prompt is None:
            return 400, {
                "error": f"'prompt' must be a non-empty string of at most {_MAX_PROMPT} characters"
            }
        return 200, service.inspect(prompt)
    return 404, {"error": f"no route for {method} {path}"}


def handle(
    method: str, path: str, body: Mapping[str, Any], service: GatewayService
) -> tuple[int, JsonObject]:
    """Route a request, recording per-route metrics, and return status and payload."""

    if method == "GET" and path == "/ready":
        return 200, {"status": "ready"}
    start = time.perf_counter()
    status, payload = _route(method, path, body, service)
    service.metrics.observe(
        f"{method} {path}", (time.perf_counter() - start) * 1000.0, error=status >= 400
    )
    return status, payload


class _Handler(BaseHTTPRequestHandler):  # pragma: no cover - exercised over sockets
    service: GatewayService

    def _respond(self, status: int, payload: JsonObject) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path == "/metrics":
            body = self.service.metrics.render_prometheus().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        status, payload = handle("GET", self.path, {}, self.service)
        self._respond(status, payload)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._respond(400, {"error": "request body is not valid JSON"})
            return
        status, payload = handle("POST", self.path, body, self.service)
        self._respond(status, payload)

    def log_message(self, *_: Any) -> None:
        return


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:  # pragma: no cover
    """Start the HTTP service (blocking)."""

    handler = type("_BoundHandler", (_Handler,), {"service": GatewayService.with_provider()})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"llm-gateway service listening on http://{host}:{port}")
    server.serve_forever()
