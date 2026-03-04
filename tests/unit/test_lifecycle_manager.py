from __future__ import annotations

import pytest

from core.memory.lifecycle_manager import (
    InvalidStateTransitionError,
    LifecycleDecision,
    LifecycleManager,
    TaskState,
)


@pytest.mark.parametrize(
    "source,target",
    [
        (TaskState.CREATED, TaskState.ACTIVE),
        (TaskState.CREATED, TaskState.ARCHIVED),
        (TaskState.ACTIVE, TaskState.COMPLETED),
        (TaskState.ACTIVE, TaskState.ARCHIVED),
        (TaskState.COMPLETED, TaskState.ARCHIVED),
    ],
)
def test_valid_transitions_are_allowed(source: TaskState, target: TaskState) -> None:
    manager = LifecycleManager()
    manager.assert_transition(task_id=101, from_state=source, to_state=target)
    assert manager.can_transition(source, target)
    assert len(manager.get_transition_log()) == 1


@pytest.mark.parametrize(
    "source,target",
    [
        (TaskState.CREATED, TaskState.COMPLETED),
        (TaskState.COMPLETED, TaskState.ACTIVE),
        (TaskState.ARCHIVED, TaskState.CREATED),
        (TaskState.ARCHIVED, TaskState.ACTIVE),
    ],
)
def test_invalid_transitions_are_rejected(source: TaskState, target: TaskState) -> None:
    manager = LifecycleManager()
    with pytest.raises(InvalidStateTransitionError):
        manager.assert_transition(task_id=102, from_state=source, to_state=target)


def test_unknown_state_raises_error() -> None:
    manager = LifecycleManager()
    with pytest.raises(InvalidStateTransitionError):
        manager.assert_transition(task_id=103, from_state="CREATED", to_state="UNKNOWN")


def test_external_authorizer_is_used_when_configured() -> None:
    calls: list[tuple[int, TaskState, TaskState]] = []

    def authorizer(task_id: int, from_state: TaskState, to_state: TaskState) -> LifecycleDecision:
        calls.append((task_id, from_state, to_state))
        return LifecycleDecision(allowed=True)

    manager = LifecycleManager(transition_authorizer=authorizer, allow_legacy_fallback=False)
    manager.assert_transition(task_id=201, from_state=TaskState.CREATED, to_state=TaskState.COMPLETED)

    assert calls == [(201, TaskState.CREATED, TaskState.COMPLETED)]
    assert len(manager.get_transition_log()) == 1


def test_missing_authorizer_fails_closed_when_legacy_disabled() -> None:
    manager = LifecycleManager(allow_legacy_fallback=False)
    with pytest.raises(InvalidStateTransitionError):
        manager.assert_transition(task_id=202, from_state=TaskState.CREATED, to_state=TaskState.ACTIVE)
