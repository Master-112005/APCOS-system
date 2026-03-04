from __future__ import annotations

import ast
from pathlib import Path

from core.memory.lifecycle_manager import TaskState
from tests.validation.fixtures.memory_transition_load import build_memory_transition_harness


def test_denied_reopen_does_not_mutate_state() -> None:
    harness = build_memory_transition_harness()

    task_id = harness.create_task(title="No silent jump", intent_id="jump-create")
    assert harness.activate_task(task_id=task_id, intent_id="jump-activate").status == "executed"
    assert harness.complete_task(task_id=task_id, intent_id="jump-complete").status == "executed"

    before = harness.store.get_task(task_id)
    assert before is not None
    assert before.state == TaskState.COMPLETED
    transition_count_before = len(harness.lifecycle.get_transition_log())

    denied = harness.reopen_task(task_id=task_id, intent_id="jump-reopen-denied")
    assert denied.status == "rejected"
    assert denied.error_code == "INVALID_TRANSITION"

    after = harness.store.get_task(task_id)
    assert after is not None
    assert after.state == TaskState.COMPLETED
    assert after.updated_at == before.updated_at
    assert after.archived_at == before.archived_at
    assert len(harness.lifecycle.get_transition_log()) == transition_count_before


def test_memory_transition_static_safety_imports() -> None:
    root = Path(__file__).resolve().parents[3]
    target_dir = root / "tests" / "behavioral" / "memory_transitions"
    forbidden_exact = {"secure_storage", "memory_authority"}
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

