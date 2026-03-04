from __future__ import annotations

from core.cognition.challenge_logic import ChallengeLogic
from core.cognition.command_router import CommandResult, CommandRouter
from core.memory.lifecycle_manager import LifecycleManager
from core.memory.task_store import TaskStore


def _build_router() -> tuple[CommandRouter, TaskStore]:
    lifecycle = LifecycleManager()
    store = TaskStore(lifecycle_manager=lifecycle)
    router = CommandRouter(
        task_store=store,
        lifecycle_manager=lifecycle,
        challenge_logic=ChallengeLogic(),
        config_path="configs/default.yaml",
    )
    return router, store


def _assert_audit_shape(event: dict[str, object]) -> None:
    assert event["intent_id"]
    assert event["timestamp"]
    assert event["action_type"]
    assert isinstance(event["success_flag"], bool)


def test_create_task_mutation_emits_audit() -> None:
    router, _ = _build_router()
    before = len(router.get_audit_events())

    result = router.route(
        {
            "intent_id": "intent-create-1",
            "intent_type": "schedule_task",
            "entities": {"task": "Prepare weekly plan"},
            "timestamp": "2026-02-20T00:00:00+00:00",
            "confidence_score": 0.95,
        }
    )

    assert isinstance(result, CommandResult)
    assert result.status == "executed"
    assert result.action == "CREATE_TASK"

    events = router.get_audit_events()
    assert len(events) == before + 1
    event = events[-1]
    _assert_audit_shape(event)
    assert event["intent_id"] == "intent-create-1"
    assert event["action_type"] == "CREATE_TASK"
    assert event["success_flag"] is True


def test_complete_task_mutation_emits_audit() -> None:
    router, store = _build_router()
    task = store.create_task(title="Finish report")
    store.activate_task(task.task_id)
    before = len(router.get_audit_events())

    result = router.route(
        {
            "intent_id": "intent-complete-1",
            "intent_type": "mark_completed",
            "entities": {"task_id": task.task_id, "alignment_score": 1.0},
            "timestamp": "2026-02-20T00:00:00+00:00",
            "confidence_score": 0.95,
        }
    )

    assert isinstance(result, CommandResult)
    assert result.status == "executed"
    assert result.action == "COMPLETE_TASK"

    events = router.get_audit_events()
    assert len(events) == before + 1
    event = events[-1]
    _assert_audit_shape(event)
    assert event["intent_id"] == "intent-complete-1"
    assert event["action_type"] == "COMPLETE_TASK"
    assert event["success_flag"] is True


def test_cancel_task_mutation_emits_audit() -> None:
    router, store = _build_router()
    task = store.create_task(title="Archive me")
    before = len(router.get_audit_events())

    result = router.route(
        {
            "intent_id": "intent-cancel-1",
            "intent_type": "cancel_task",
            "entities": {"task_id": task.task_id, "alignment_score": 1.0},
            "timestamp": "2026-02-20T00:00:00+00:00",
            "confidence_score": 0.95,
        }
    )

    assert isinstance(result, CommandResult)
    assert result.status == "executed"
    assert result.action == "CANCEL_TASK"

    events = router.get_audit_events()
    assert len(events) == before + 1
    event = events[-1]
    _assert_audit_shape(event)
    assert event["intent_id"] == "intent-cancel-1"
    assert event["action_type"] == "CANCEL_TASK"
    assert event["success_flag"] is True


def test_error_paths_still_emit_audit_events() -> None:
    router, store = _build_router()
    task = store.create_task(title="Cannot complete directly")

    inputs_and_errors = [
        (
            {
                "intent_id": "intent-low-confidence",
                "intent_type": "schedule_task",
                "entities": {"task": "Maybe"},
                "timestamp": "2026-02-20T00:00:00+00:00",
                "confidence_score": 0.1,
            },
            "LOW_CONFIDENCE",
        ),
        (
            {
                "intent_id": "intent-invalid-entity",
                "intent_type": "schedule_task",
                "entities": {},
                "timestamp": "2026-02-20T00:00:00+00:00",
                "confidence_score": 0.95,
            },
            "INVALID_ENTITY",
        ),
        (
            {
                "intent_id": "intent-invalid-transition",
                "intent_type": "mark_completed",
                "entities": {"task_id": task.task_id, "alignment_score": 1.0},
                "timestamp": "2026-02-20T00:00:00+00:00",
                "confidence_score": 0.95,
            },
            "INVALID_TRANSITION",
        ),
    ]

    before = len(router.get_audit_events())
    for intent, expected_error in inputs_and_errors:
        result = router.route(intent)
        assert isinstance(result, CommandResult)
        assert result.status == "rejected"
        assert result.error_code == expected_error

    events = router.get_audit_events()
    assert len(events) == before + len(inputs_and_errors)
    for index, (intent, _) in enumerate(inputs_and_errors, start=1):
        event = events[-len(inputs_and_errors) + index - 1]
        _assert_audit_shape(event)
        assert event["intent_id"] == intent["intent_id"]
        assert event["success_flag"] is False
