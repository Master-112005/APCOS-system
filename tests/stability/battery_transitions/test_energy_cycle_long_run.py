from __future__ import annotations

import ast
from pathlib import Path

from tests.validation.fixtures.battery_transition_stability import (
    build_battery_transition_harness,
)


def test_energy_cycle_long_run_completes() -> None:
    harness = build_battery_transition_harness()
    reports = harness.run_cycle()

    assert len(reports) == 5
    assert [report.battery_percent for report in reports] == [60, 30, 10, 5, 70]
    assert [report.mode for report in reports] == ["NORMAL", "REDUCED", "CRITICAL", "CRITICAL", "NORMAL"]

    for report in reports:
        assert isinstance(report.voice_response, str)
        assert report.voice_response

    assert reports[0].reasoning_allowed is True
    assert reports[1].reasoning_allowed is True
    assert reports[2].reasoning_allowed is False
    assert reports[3].reasoning_allowed is False
    assert reports[4].reasoning_allowed is True


def test_battery_transition_static_safety_imports() -> None:
    root = Path(__file__).resolve().parents[3]
    target_dir = root / "tests" / "stability" / "battery_transitions"
    forbidden_exact = {"memory_authority", "secure_storage"}
    forbidden_prefixes = ("os.src", "os.src.runtime", "os.src.identity")

    violations: list[str] = []
    for file_path in sorted(target_dir.glob("test_*.py")):
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    if name.startswith(forbidden_prefixes) or name in forbidden_exact:
                        violations.append(f"{file_path}:{node.lineno}:{name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith(forbidden_prefixes) or module in forbidden_exact:
                    violations.append(f"{file_path}:{node.lineno}:{module}")

    assert not violations, "Forbidden imports detected:\n" + "\n".join(violations)
