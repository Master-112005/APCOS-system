from __future__ import annotations

from datetime import datetime, timezone

from core.cognition.challenge_logic import ChallengeLogic
from core.cognition.command_router import CommandRouter
from core.memory.lifecycle_manager import LifecycleDecision, LifecycleManager, TaskState
from core.memory.task_store import TaskStore
from tests.validation.fixtures.multi_source_sync import MockMobileConnector, MockSyncDaemon


def _intent(
    *,
    intent_type: str,
    entities: dict[str, object],
    intent_id: str,
) -> dict[str, object]:
    return {
        "intent_id": intent_id,
        "intent_type": intent_type,
        "entities": entities,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "confidence_score": 0.95,
    }


def test_denied_transition_preserves_router_integrity_and_state() -> None:
    transition_checks: list[tuple[int, TaskState, TaskState]] = []

    def transition_authorizer(task_id: int, from_state: TaskState, to_state: TaskState) -> LifecycleDecision:
        transition_checks.append((task_id, from_state, to_state))
        if from_state == TaskState.CREATED and to_state == TaskState.COMPLETED:
            return LifecycleDecision(allowed=False, reason="DENIED_CREATED_TO_COMPLETED")
        return LifecycleDecision(allowed=True, reason=None)

    lifecycle = LifecycleManager(transition_authorizer=transition_authorizer, allow_legacy_fallback=False)
    store = TaskStore(lifecycle_manager=lifecycle)
    router = CommandRouter(
        task_store=store,
        lifecycle_manager=lifecycle,
        challenge_logic=ChallengeLogic(),
        config_path="configs/default.yaml",
    )
    mobile = MockMobileConnector()
    sync = MockSyncDaemon()

    create_result = router.route(
        _intent(
            intent_type="schedule_task",
            entities={"task": "Authority-sensitive task"},
            intent_id="intent-create-authority",
        )
    )
    assert create_result.status == "executed"
    task_id = int(create_result.metadata["task_id"])
    task_before = store.get_task(task_id)
    assert task_before is not None

    # Simulate concurrent external load envelopes before routed transition attempt.
    for index in range(12):
        sync.emit(
            source_id=f"sync-authority-{index % 3}",
            sync_type="STATE_RECONCILE",
            payload={"external_revision": index},
            correlation_id=f"sync-auth-{index}",
            merge_hint={"source_priority": "normal", "version": "v1"},
        )
        mobile.emit(
            action="reminder_ack",
            payload={"task_id": task_id},
            correlation_id=f"mobile-auth-{index}",
        )

    audits_before_denial = len(router.get_audit_events())

    denied_result = router.route(
        _intent(
            intent_type="mark_completed",
            entities={"task_id": task_id, "alignment_score": 1.0},
            intent_id="intent-denied-transition",
        )
    )
    assert denied_result.status == "rejected"
    assert denied_result.error_code == "INVALID_TRANSITION"

    # Transition validator was invoked and denied CREATED -> COMPLETED.
    assert transition_checks
    denied_transition = transition_checks[-1]
    assert denied_transition[0] == task_id
    assert denied_transition[1] == TaskState.CREATED
    assert denied_transition[2] == TaskState.COMPLETED

    # Memory state remains unchanged and row metadata remains unchanged.
    task_after = store.get_task(task_id)
    assert task_after is not None
    assert task_after.state == TaskState.CREATED
    assert task_after.updated_at == task_before.updated_at
    assert task_after.archived_at == task_before.archived_at

    audits_after = router.get_audit_events()
    assert len(audits_after) == audits_before_denial + 1
    last_audit = audits_after[-1]
    assert last_audit["intent_id"] == "intent-denied-transition"
    assert last_audit["action_type"] == "COMPLETE_TASK"
    assert last_audit["success_flag"] is False
