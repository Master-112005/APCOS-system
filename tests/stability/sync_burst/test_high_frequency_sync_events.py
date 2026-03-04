from __future__ import annotations

import ast
from pathlib import Path

from tests.validation.fixtures.sync_burst_stability import (
    build_sync_burst_stability_harness,
)


def test_high_frequency_sync_events_no_loss_or_duplicates() -> None:
    harness = build_sync_burst_stability_harness(
        max_queue_size=512,
        drain_every=8,
        drain_batch_size=6,
    )
    metrics = harness.run_burst(iterations=800, mobile_every=5)
    expected_mobile = 160
    expected_total = 960

    assert metrics.sync_sent == 800
    assert metrics.mobile_sent == expected_mobile
    assert metrics.total_sent == expected_total
    assert metrics.processed_count == expected_total
    assert metrics.duplicate_count == 0
    assert metrics.overflow_detected is False
    assert metrics.pending_queue == 0
    assert len(harness.bridge.messages) == expected_total
    assert all(msg.get("message_type") == "EVENT" for msg in harness.bridge.messages)


def test_sync_burst_static_safety_imports() -> None:
    root = Path(__file__).resolve().parents[3]
    target_dir = root / "tests" / "stability" / "sync_burst"
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
