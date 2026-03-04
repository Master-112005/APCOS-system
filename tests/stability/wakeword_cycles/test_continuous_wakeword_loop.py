from __future__ import annotations

import ast
from pathlib import Path
import statistics

from tests.validation.fixtures.wakeword_stability import (
    build_wakeword_stability_harness,
)


def test_continuous_wakeword_loop_1000_cycles() -> None:
    harness = build_wakeword_stability_harness(transcript="status check")
    measurements = harness.run_cycles(1000)

    assert len(measurements) == 1000
    assert harness.controller.calls == 1000
    assert all(item.response == "Advisory: status check" for item in measurements)

    warm_latencies = [item.wake_to_response_ms for item in measurements[1:]]
    early_window_avg = statistics.fmean(warm_latencies[:250])
    late_window_avg = statistics.fmean(warm_latencies[-250:])

    assert late_window_avg <= (early_window_avg * 2.0) + 1.0
    assert max(warm_latencies) <= (statistics.fmean(warm_latencies) * 10.0) + 20.0


def test_wakeword_cycle_static_safety_imports() -> None:
    root = Path(__file__).resolve().parents[3]
    target_dir = root / "tests" / "stability" / "wakeword_cycles"
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
