from __future__ import annotations

from datetime import datetime, timezone

from core.cognition.challenge_logic import ChallengeLogic
from core.cognition.command_router import CommandRouter
from core.memory.lifecycle_manager import LifecycleManager, TaskState
from core.memory.task_store import TaskStore


def make_router(*, challenge_threshold: float = 0.5) -> tuple[CommandRouter, TaskStore]:
    lifecycle = LifecycleManager()
    store = TaskStore(lifecycle_manager=lifecycle)
    challenge = ChallengeLogic(challenge_threshold=challenge_threshold)
    router = CommandRouter(
        task_store=store,
        lifecycle_manager=lifecycle,
        challenge_logic=challenge,
        config_path="configs/default.yaml",
    )
    return router, store


def test_valid_create_task_routing_executes_and_persists() -> None:
    router, store = make_router()
    intent = {
        "intent_type": "schedule_task",
        "entities": {"task": "Plan sprint", "due_at": "2026-02-20T10:00:00+00:00"},
        "timestamp": "2026-02-19T08:30:00+00:00",
        "confidence_score": 0.92,
    }

    result = router.route(intent)
    assert result.status == "executed"
    assert result.action == "CREATE_TASK"
    assert result.error_code is None
    assert "task_id" in result.metadata

    task = store.get_task(result.metadata["task_id"])
    assert task is not None
    assert task.state == TaskState.CREATED


def test_low_confidence_is_rejected() -> None:
    router, _ = make_router()
    intent = {
        "intent_type": "schedule_task",
        "entities": {"task": "Plan sprint"},
        "timestamp": "2026-02-19T08:30:00+00:00",
        "confidence_score": 0.30,
    }

    result = router.route(intent)
    assert result.status == "rejected"
    assert result.error_code == "LOW_CONFIDENCE"


def test_invalid_intent_shape_is_rejected() -> None:
    router, _ = make_router()
    invalid_intent = {
        "intent_type": "schedule_task",
        "entities": {"task": "Plan sprint"},
        "confidence_score": 0.9,
    }

    result = router.route(invalid_intent)
    assert result.status == "rejected"
    assert result.error_code == "INVALID_INTENT_SHAPE"


def test_challenge_flow_returns_challenge_required_without_mutation() -> None:
    router, store = make_router(challenge_threshold=0.5)
    task = store.create_task(title="Workout", goal="Improve fitness")
    active = store.activate_task(task.task_id)
    assert active.state == TaskState.ACTIVE

    intent = {
        "intent_type": "mark_completed",
        "entities": {
            "task_id": task.task_id,
            "declared_goal": "Improve fitness",
            "alignment_score": 0.2,
        },
        "timestamp": datetime(2026, 2, 19, 9, 0, tzinfo=timezone.utc),
        "confidence_score": 0.95,
    }

    result = router.route(intent)
    assert result.status == "challenge_required"
    assert result.action == "COMPLETE_TASK"
    assert result.challenge_payload is not None

    current = store.get_task(task.task_id)
    assert current is not None
    assert current.state == TaskState.ACTIVE


def test_invalid_transition_is_normalized_to_structured_error() -> None:
    router, store = make_router()
    task = store.create_task(title="Stretching")
    assert task.state == TaskState.CREATED

    intent = {
        "intent_type": "mark_completed",
        "entities": {"task_id": task.task_id, "alignment_score": 1.0},
        "timestamp": "2026-02-19T09:15:00+00:00",
        "confidence_score": 0.97,
    }
    result = router.route(intent)

    assert result.status == "rejected"
    assert result.action == "COMPLETE_TASK"
    assert result.error_code == "INVALID_TRANSITION"


def test_every_route_emits_audit_record() -> None:
    router, _ = make_router()

    valid = {
        "intent_type": "schedule_task",
        "entities": {"task": "Read design doc", "sensitive": True},
        "timestamp": "2026-02-19T08:30:00+00:00",
        "confidence_score": 0.92,
    }
    invalid = {
        "intent_type": "schedule_task",
        "entities": {"task": "Read design doc"},
        "timestamp": "2026-02-19T08:30:00+00:00",
        "confidence_score": 0.2,
    }

    router.route(valid)
    router.route(invalid)

    events = router.get_audit_events()
    assert len(events) == 2
    assert events[0]["audit_id"]
    assert events[1]["audit_id"]
    assert events[0]["entities"]["sensitive"] is True
    assert "task" not in events[0]["entities"]
