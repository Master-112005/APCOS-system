from __future__ import annotations

import ast
import os
from pathlib import Path
from time import perf_counter

from core.behavior.calibration_engine import CalibrationEngine


def test_calibration_10000_updates_within_budget() -> None:
    engine = CalibrationEngine(config_path="configs/default.yaml")
    threshold = 0.7
    metrics = {
        "accepted": 5,
        "rejected": 3,
        "ignored": 2,
        "overrides": 1,
        "acceptance_rate": 0.5,
    }
    max_seconds = float(os.getenv("APCOS_CALIBRATION_PERF_MAX_SEC", "0.5"))

    started = perf_counter()
    for _ in range(10_000):
        threshold = engine.update_threshold(threshold, metrics)
    elapsed = perf_counter() - started

    assert threshold >= engine.config.min_threshold
    assert threshold <= engine.config.max_threshold
    assert elapsed < max_seconds, (
        f"Calibration performance budget exceeded: {elapsed:.6f}s >= {max_seconds:.6f}s"
    )


def test_calibration_engine_has_no_blocking_or_dynamic_import_calls() -> None:
    source_path = Path("core/behavior/calibration_engine.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    disallowed_call_names = {"open", "sleep", "import_module"}

    target_function = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "update_threshold":
            target_function = node
            break
    assert target_function is not None, "update_threshold() definition was not found"

    violations: list[str] = []
    for node in ast.walk(target_function):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id in disallowed_call_names:
            violations.append(f"line {node.lineno}: {node.func.id}()")
        if isinstance(node.func, ast.Attribute) and node.func.attr in disallowed_call_names:
            violations.append(f"line {node.lineno}: .{node.func.attr}()")

    assert not violations, "Disallowed calls found in calibration engine:\n" + "\n".join(violations)
