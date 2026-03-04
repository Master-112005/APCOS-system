"""Fixtures for behavioral memory transition load validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from core.cognition.challenge_logic import ChallengeLogic
from core.cognition.command_router import ActionExecution, CommandRouter
from core.memory.lifecycle_manager import LifecycleManager
from core.memory.task_store import TaskRecord, TaskStore


def _task_ref_validator(entities: dict[str, Any]) -> None:
    task_id = entities.get("task_id")
    if not isinstance(task_id, int) or task_id <= 0:
        raise ValueError("task_id must be positive integer")


def _build_transition_handler(
    *,
    store: TaskStore,
    action_type: str,
    transition_fn: Callable[[int], TaskRecord],
) -> Callable[[dict[str, Any]], ActionExecution]:
    def _handler(entities: dict[str, Any]) -> ActionExecution:
        task_id = int(entities["task_id"])
        task = store.get_task(task_id)
        if task is None:
            raise KeyError(f"task_id {task_id} not found")
        before = task.state.value
        updated = transition_fn(task_id)
        return ActionExecution(
            action_type=action_type,
            lifecycle_before=before,
            lifecycle_after=updated.state.value,
            metadata={"task_id": task_id},
        )

    return _handler


@dataclass
class MemoryTransitionHarness:
    """Router-centric transition harness for high-frequency behavior tests."""

    router: CommandRouter
    store: TaskStore
    lifecycle: LifecycleManager

    def route(self, *, intent_type: str, entities: dict[str, Any], intent_id: str) -> Any:
        return self.router.route(
            {
                "intent_id": intent_id,
                "intent_type": intent_type,
                "entities": entities,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "confidence_score": 0.95,
            }
        )

    def create_task(self, *, title: str, intent_id: str) -> int:
        result = self.route(
            intent_type="schedule_task",
            entities={"task": title},
            intent_id=intent_id,
        )
        if result.status != "executed":
            raise RuntimeError(f"create_task failed: {result.error_code}")
        return int(result.metadata["task_id"])

    def activate_task(self, *, task_id: int, intent_id: str) -> Any:
        return self.route(
            intent_type="activate_task",
            entities={"task_id": task_id},
            intent_id=intent_id,
        )

    def complete_task(self, *, task_id: int, intent_id: str) -> Any:
        return self.route(
            intent_type="mark_completed",
            entities={"task_id": task_id, "alignment_score": 1.0},
            intent_id=intent_id,
        )

    def archive_task(self, *, task_id: int, intent_id: str) -> Any:
        return self.route(
            intent_type="cancel_task",
            entities={"task_id": task_id, "alignment_score": 1.0},
            intent_id=intent_id,
        )

    def reopen_task(self, *, task_id: int, intent_id: str) -> Any:
        return self.route(
            intent_type="reopen_task",
            entities={"task_id": task_id},
            intent_id=intent_id,
        )


def build_memory_transition_harness() -> MemoryTransitionHarness:
    """Create harness with routed ACTIVE and reopen transition handlers."""
    lifecycle = LifecycleManager()
    store = TaskStore(lifecycle_manager=lifecycle)
    router = CommandRouter(
        task_store=store,
        lifecycle_manager=lifecycle,
        challenge_logic=ChallengeLogic(),
        config_path="configs/default.yaml",
    )

    router.register_action_handler(
        "activate_task",
        _build_transition_handler(
            store=store,
            action_type="ACTIVATE_TASK",
            transition_fn=store.activate_task,
        ),
        action_type="ACTIVATE_TASK",
        validator=_task_ref_validator,
        challengeable=False,
    )

    router.register_action_handler(
        "reopen_task",
        _build_transition_handler(
            store=store,
            action_type="REOPEN_TASK",
            transition_fn=store.activate_task,
        ),
        action_type="REOPEN_TASK",
        validator=_task_ref_validator,
        challengeable=False,
    )

    return MemoryTransitionHarness(router=router, store=store, lifecycle=lifecycle)

