"""LLM Gateway - a safety proxy for language-model APIs, from scratch."""

from __future__ import annotations

from llm_gateway.data import SuiteCase, adversarial_suite
from llm_gateway.evaluation import DefenseReport, evaluate
from llm_gateway.gateway import Gateway, GatewayResponse, GatewayStats
from llm_gateway.injection import InjectionReport, assess_injection
from llm_gateway.pii import RedactionReport, contains_pii, redact
from llm_gateway.policy import PolicyReport, SemanticCache, check_output
from llm_gateway.provider import AnthropicProvider, FakeProvider, Provider

__version__ = "0.1.0"

__all__ = [
    "AnthropicProvider",
    "DefenseReport",
    "FakeProvider",
    "Gateway",
    "GatewayResponse",
    "GatewayStats",
    "InjectionReport",
    "PolicyReport",
    "Provider",
    "RedactionReport",
    "SemanticCache",
    "SuiteCase",
    "__version__",
    "adversarial_suite",
    "assess_injection",
    "check_output",
    "contains_pii",
    "evaluate",
    "redact",
]
