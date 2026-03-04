from __future__ import annotations

import builtins
import importlib
import os
from time import perf_counter

from core.cognition.command_router import CommandResult
from core.cognition.explanation_engine import ExplanationEngine


def test_explanation_10000_calls_within_budget(monkeypatch) -> None:
    engine = ExplanationEngine()
    result = CommandResult(
        status="executed",
        action="CREATE_TASK",
        audit_id="audit-perf",
        message_key="COMMAND_EXECUTED",
        metadata={},
    )
    max_seconds = float(os.getenv("APCOS_EXPLANATION_PERF_MAX_SEC", "0.5"))

    original_open = builtins.open
    original_import_module = importlib.import_module

    def _forbidden_open(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("Explanation engine must not perform file I/O")

    def _forbidden_import_module(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("Explanation engine must not perform dynamic imports")

    monkeypatch.setattr(builtins, "open", _forbidden_open)
    monkeypatch.setattr(importlib, "import_module", _forbidden_import_module)

    started = perf_counter()
    last = ""
    for _ in range(10_000):
        last = engine.generate_response(result)
    elapsed = perf_counter() - started

    monkeypatch.setattr(builtins, "open", original_open)
    monkeypatch.setattr(importlib, "import_module", original_import_module)

    assert last == "Your task has been scheduled successfully."
    assert elapsed < max_seconds, (
        f"Explanation performance budget exceeded: {elapsed:.6f}s >= {max_seconds:.6f}s"
    )
