from __future__ import annotations

from core.memory.lifecycle_manager import TaskState
from tests.validation.fixtures.memory_transition_load import build_memory_transition_harness


def test_transition_flood_under_load() -> None:
    harness = build_memory_transition_harness()
    task_count = 20  # 80 routed mutation attempts total.

    task_ids = [
        harness.create_task(title=f"Load Task {index}", intent_id=f"load-create-{index}")
        for index in range(task_count)
    ]

    for index, task_id in enumerate(task_ids):
        result = harness.activate_task(task_id=task_id, intent_id=f"load-activate-{index}")
        assert result.status == "executed"
        assert result.action == "ACTIVATE_TASK"

    for index, task_id in enumerate(task_ids):
        # ACTIVE -> COMPLETED maps to "dormant" behavior in memory authority semantics.
        result = harness.complete_task(task_id=task_id, intent_id=f"load-complete-{index}")
        assert result.status == "executed"
        assert result.action == "COMPLETE_TASK"

    for index, task_id in enumerate(task_ids):
        result = harness.archive_task(task_id=task_id, intent_id=f"load-archive-{index}")
        assert result.status == "executed"
        assert result.action == "CANCEL_TASK"

    final_tasks = harness.store.list_tasks(include_archived=True)
    assert len(final_tasks) == task_count
    assert all(task.state == TaskState.ARCHIVED for task in final_tasks)

    transitions = harness.lifecycle.get_transition_log()
    assert len(transitions) == task_count * 3
    allowed_edges = {
        (TaskState.CREATED, TaskState.ACTIVE),
        (TaskState.ACTIVE, TaskState.COMPLETED),
        (TaskState.COMPLETED, TaskState.ARCHIVED),
    }
    assert all((record.from_state, record.to_state) in allowed_edges for record in transitions)

    audit_events = harness.router.get_audit_events()
    assert len(audit_events) == task_count * 4
    assert all(bool(event["success_flag"]) for event in audit_events)

