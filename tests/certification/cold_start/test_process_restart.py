from __future__ import annotations

from datetime import datetime, timezone

from core.cognition.challenge_logic import ChallengeLogic
from core.cognition.command_router import CommandRouter
from core.identity.identity_resolver import IdentityResolver
from core.memory.lifecycle_manager import LifecycleManager
from core.memory.task_store import TaskStore


def _build_runtime(db_path: str) -> tuple[TaskStore, CommandRouter]:
    lifecycle = LifecycleManager()
    store = TaskStore(db_path=db_path, lifecycle_manager=lifecycle)
    router = CommandRouter(
        task_store=store,
        lifecycle_manager=lifecycle,
        challenge_logic=ChallengeLogic(),
        config_path="configs/default.yaml",
    )
    return store, router


def _create_task_via_router(router: CommandRouter, *, title: str) -> None:
    intent = {
        "intent_id": "cold-start-create-1",
        "intent_type": "create_task",
        "entities": {"task": title, "goal": "restart-cert"},
        "timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        "confidence_score": 0.99,
    }
    result = router.route(intent)
    assert result.status == "executed"


def test_process_restart_preserves_memory_and_identity(tmp_path) -> None:
    db_path = str(tmp_path / "cold_start_tasks.db")
    resolver = IdentityResolver()

    first_identity = resolver.default_identity()
    store_a, router_a = _build_runtime(db_path)
    _create_task_via_router(router_a, title="Cold-start certification task")
    tasks_before = store_a.list_tasks(include_archived=True)
    store_a.close()

    second_identity = resolver.default_identity()
    store_b, _router_b = _build_runtime(db_path)
    tasks_after = store_b.list_tasks(include_archived=True)
    store_b.close()

    assert len(tasks_before) == 1
    assert len(tasks_after) == 1
    assert tasks_after[0].title == "Cold-start certification task"
    assert tasks_after[0].state.value == "CREATED"

    assert first_identity.tier == second_identity.tier
    assert first_identity.authenticated is True
    assert second_identity.authenticated is True
