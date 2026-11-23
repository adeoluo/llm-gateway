"""The smoke-suite table in the README is what `python -m llm_gateway report` prints."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from llm_gateway.cli import main

README = (Path(__file__).resolve().parent.parent / "README.md").read_text()


def test_readme_smoke_table_matches_the_report(capsys: pytest.CaptureFixture[str]) -> None:
    main(["report"])
    out = capsys.readouterr().out
    values = {
        "injection rule precision": re.search(r"injection precision=([\d.]+)", out),
        "injection rule recall": re.search(r"recall=([\d.]+); PII", out),
        "PII redaction recall": re.search(r"PII redaction recall=([\d.]+)", out),
        "semantic cache hit rate on repeats": re.search(r"cache hit rate=([\d.]+)", out),
    }
    for label, match in values.items():
        assert match, (label, out)
        assert f"| {label} | {match[1]} |" in README, (label, match[1])
