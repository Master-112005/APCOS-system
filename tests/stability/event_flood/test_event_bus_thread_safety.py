from __future__ import annotations

import ast
from pathlib import Path
import threading

from tests.validation.fixtures.event_flood_stability import (
    build_event_flood_stability_harness,
)


def test_event_bus_thread_safety_under_internal_flood() -> None:
    start_threads = threading.active_count()
    harness = build_event_flood_stability_harness()
    metrics = harness.run_flood(iterations=1000)
    end_threads = threading.active_count()

    expected_total = 1000 * 4
    assert metrics.total_published == expected_total
    assert metrics.processed_events == expected_total
    assert metrics.state_updates == expected_total
    assert metrics.duplicate_correlation_count == 0
    assert harness.state_update_messages_are_valid() is True
    assert end_threads - start_threads <= 1


def test_event_flood_static_safety_imports() -> None:
    root = Path(__file__).resolve().parents[3]
    target_dir = root / "tests" / "stability" / "event_flood"
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
