from __future__ import annotations

import ast
from pathlib import Path

from tests.certification.deterministic_replay.replay_fixture import run_replay_twice


def test_replay_runs_produce_identical_hashes() -> None:
    run_a, run_b = run_replay_twice()

    assert run_a.stable_hash() == run_b.stable_hash()
    assert run_a.ipc_envelopes == run_b.ipc_envelopes
    assert run_a.router_results == run_b.router_results
    assert run_a.reasoning_outputs == run_b.reasoning_outputs
    assert run_a.lifecycle_transitions == run_b.lifecycle_transitions
    assert run_a.task_states == run_b.task_states


def test_replay_lifecycle_and_reasoning_structure_locked() -> None:
    run_a, _ = run_replay_twice()

    assert run_a.lifecycle_transitions == (
        {"task_id": 1, "from_state": "CREATED", "to_state": "ARCHIVED"},
    )

    assert len(run_a.reasoning_outputs) == 1
    structure_keys = run_a.reasoning_outputs[0]["structure_keys"]
    assert structure_keys == [
        "blocked_reason",
        "correlation_id",
        "safe_to_present",
        "strategy_steps",
        "summary",
    ]


def test_replay_static_safety_imports() -> None:
    root = Path(__file__).resolve().parents[3]
    target_dir = root / "tests" / "certification" / "deterministic_replay"

    forbidden_prefixes = ("os.src",)
    forbidden_modules = {
        "core.memory.task_store",
        "core.memory.lifecycle_manager",
        "core.cognition.command_router",
    }

    violations: list[str] = []
    for file_path in sorted(target_dir.glob("*.py")):
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    if name.startswith(forbidden_prefixes):
                        violations.append(f"{file_path}:{node.lineno}:{name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith(forbidden_prefixes):
                    violations.append(f"{file_path}:{node.lineno}:{module}")

    assert not violations, "Forbidden imports detected:\n" + "\n".join(violations)
