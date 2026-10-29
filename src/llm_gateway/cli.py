"""Command line interface for the language-model safety gateway."""

from __future__ import annotations

import argparse

from llm_gateway.evaluation import evaluate
from llm_gateway.gateway import Gateway
from llm_gateway.injection import assess_injection
from llm_gateway.pii import redact


def _cmd_report(_: argparse.Namespace) -> None:
    report = evaluate()
    print("Gateway defenses on the adversarial suite:")
    print(f"  {report.format()}")


def _cmd_complete(args: argparse.Namespace) -> None:
    gateway = Gateway()
    response = gateway.handle(args.prompt)
    print(f"status:  {response.status}")
    if response.reasons:
        print(f"reasons: {', '.join(response.reasons)}")
    if response.text:
        print(f"text:    {response.text}")
    print(f"cached:  {response.cached}  input_pii_redacted: {response.input_pii_redacted}")


def _cmd_inspect(args: argparse.Namespace) -> None:
    injection = assess_injection(args.prompt)
    redaction = redact(args.prompt)
    print(f"injection score: {injection.score} blocked: {injection.blocked}")
    if injection.triggers:
        print(f"  triggers: {', '.join(injection.triggers)}")
    print(f"PII found: {redaction.counts or 'none'}")
    print(f"redacted: {redaction.text}")


def _cmd_serve(args: argparse.Namespace) -> None:
    from llm_gateway.service import serve

    serve(host=args.host, port=args.port)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="llm-gateway", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("report", help="defense quality and cache savings on the adversarial suite")

    complete = sub.add_parser("complete", help="run a prompt through the full safety pipeline")
    complete.add_argument("prompt")

    inspect = sub.add_parser("inspect", help="assess a prompt for injection and PII")
    inspect.add_argument("prompt")

    serve = sub.add_parser("serve", help="start the HTTP service")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    handlers = {
        "report": _cmd_report,
        "complete": _cmd_complete,
        "inspect": _cmd_inspect,
        "serve": _cmd_serve,
    }
    args = parser.parse_args(argv)
    handlers[args.command](args)


if __name__ == "__main__":
    main()
