from __future__ import annotations

import ast
from pathlib import Path

from tests.validation.fixtures.extended_runtime_stability import (
    run_extended_runtime_simulation,
)


def test_extended_runtime_cycles_complete_with_invariants() -> None:
    metrics = run_extended_runtime_simulation(10_000)

    assert metrics.requested_cycles == 10_000
    assert metrics.completed_cycles == 10_000
    assert metrics.total_elapsed_ms < 15_000.0

    assert metrics.sync_event_count == 10_000
    assert metrics.sync_processed_count == 10_000
    assert metrics.sync_invalid_message_count == 0
    assert metrics.sync_max_backlog <= 1

    assert metrics.asr_model_load_count == 1
    assert metrics.asr_pipeline_build_count == 1
    assert metrics.tts_pipeline_load_count == 1

    assert metrics.llm_allowed_count > 0
    assert metrics.llm_denied_count > 0
    assert metrics.llm_downgraded_count > 0
    assert metrics.unsafe_reasoning_outputs == 0

    assert "STRATEGIC" in metrics.energy_modes_seen
    assert "REDUCED" in metrics.energy_modes_seen
    assert "SILENT" in metrics.energy_modes_seen
    assert metrics.energy_transition_count >= 200

    assert metrics.voice_allowed_count > 0
    assert metrics.voice_denied_count == 0
    assert metrics.proactive_executed_count > 0
    assert metrics.proactive_suppressed_by_cooldown > 0


def test_extended_runtime_static_safety_imports() -> None:
    root = Path(__file__).resolve().parents[3]
    target_dir = root / "tests" / "stability" / "extended_runtime"
    forbidden_exact = {"memory_authority", "secure_storage"}
    forbidden_prefixes = ("os.src", "os.src.runtime", "os.src.identity")
    forbidden_router_modules = {
        "core.cognition.command_router",
        "core.memory.task_store",
        "core.memory.lifecycle_manager",
    }

    violations: list[str] = []
    for file_path in sorted(target_dir.glob("test_*.py")):
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    if (
                        name.startswith(forbidden_prefixes)
                        or name in forbidden_exact
                        or name in forbidden_router_modules
                    ):
                        violations.append(f"{file_path}:{node.lineno}:{name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if (
                    module.startswith(forbidden_prefixes)
                    or module in forbidden_exact
                    or module in forbidden_router_modules
                ):
                    violations.append(f"{file_path}:{node.lineno}:{module}")

    assert not violations, "Forbidden imports detected:\n" + "\n".join(violations)
