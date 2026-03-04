from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

from core.cognition.challenge_logic import ChallengeLogic
from core.cognition.command_router import CommandRouter
from core.memory.lifecycle_manager import LifecycleManager, TaskState
from core.memory.task_store import TaskStore
from tests.validation.fixtures.multi_source_sync import (
    MockIdentityContext,
    MockMobileConnector,
    MockSyncDaemon,
)


def _build_router_stack() -> tuple[CommandRouter, TaskStore]:
    lifecycle = LifecycleManager()
    store = TaskStore(lifecycle_manager=lifecycle)
    router = CommandRouter(
        task_store=store,
        lifecycle_manager=lifecycle,
        challenge_logic=ChallengeLogic(),
        config_path="configs/default.yaml",
    )
    return router, store


def _schedule_intent(*, title: str, intent_id: str) -> dict[str, object]:
    return {
        "intent_id": intent_id,
        "intent_type": "schedule_task",
        "entities": {"task": title},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "confidence_score": 0.95,
    }


def test_sync_burst_integrity_with_interleaved_mobile_events() -> None:
    router, store = _build_router_stack()
    mobile = MockMobileConnector()
    sync = MockSyncDaemon()
    identity = MockIdentityContext(user_id="owner-1", tier="OWNER", authenticated=True)

    iterations = 30
    start_audit_count = len(router.get_audit_events())

    for index in range(iterations):
        sync_envelope = sync.emit(
            source_id=f"mobile-source-{index % 3}",
            sync_type="TASK_UPDATE",
            payload={"external_task_id": f"ext-{index}", "identity": identity.user_id},
            correlation_id=f"sync-{index}",
            merge_hint={"source_priority": "normal", "version": "v1"},
        )
        assert sync_envelope["message_type"] == "EVENT"

        mobile_envelope = mobile.emit(
            action="create_task",
            payload={"task": f"Task {index}", "identity_tier": identity.tier},
            correlation_id=f"mobile-{index}",
        )
        assert mobile_envelope["message_type"] == "EVENT"

        result = router.route(
            _schedule_intent(
                title=f"Task {index}",
                intent_id=f"intent-{index}",
            )
        )
        assert result.status == "executed"
        assert result.action == "CREATE_TASK"

    tasks = store.list_tasks(include_archived=True)
    task_ids = [task.task_id for task in tasks]
    assert len(task_ids) == iterations
    assert len(set(task_ids)) == iterations

    valid_states = {state.value for state in TaskState}
    observed_states = {task.state.value for task in tasks}
    assert observed_states.issubset(valid_states)

    new_events = router.get_audit_events()[start_audit_count:]
    executed_events = [event for event in new_events if bool(event["success_flag"])]
    assert len(executed_events) == iterations
    assert all(event["action_type"] == "CREATE_TASK" for event in executed_events)


def test_multi_source_sync_static_safety_imports() -> None:
    root = Path(__file__).resolve().parents[3]
    target_dir = root / "tests" / "behavioral" / "multi_source_sync"
    forbidden_prefixes = ("os.src", "os.src.runtime", "os.src.identity")

    violations: list[str] = []
    for file_path in sorted(target_dir.glob("test_*.py")):
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

