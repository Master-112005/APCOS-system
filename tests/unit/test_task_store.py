from __future__ import annotations

import pytest

from core.memory.lifecycle_manager import InvalidStateTransitionError, TaskState
from core.memory.task_store import TaskStore


def test_task_store_create_read_and_archive() -> None:
    store = TaskStore()
    task = store.create_task(
        title="Finish architecture doc",
        description="Complete phase-1 baseline",
        goal="Ship deterministic memory",
        due_at="2026-02-21T10:00:00+00:00",
        priority=2,
    )

    assert task.state == TaskState.CREATED
    fetched = store.get_task(task.task_id)
    assert fetched is not None
    assert fetched.title == "Finish architecture doc"
    assert fetched.description == "Complete phase-1 baseline"
    assert fetched.goal == "Ship deterministic memory"

    archived = store.archive_task(task.task_id)
    assert archived.state == TaskState.ARCHIVED
    assert archived.archived_at is not None


def test_invalid_transition_rejected_by_task_store() -> None:
    store = TaskStore()
    task = store.create_task(title="Workout")

    with pytest.raises(InvalidStateTransitionError):
        store.complete_task(task.task_id)


def test_delete_is_blocked() -> None:
    store = TaskStore()
    task = store.create_task(title="Never delete me")

    with pytest.raises(RuntimeError):
        store.delete_task(task.task_id)
