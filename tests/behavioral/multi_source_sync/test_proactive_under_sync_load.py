from __future__ import annotations

from datetime import datetime, timezone

from core.behavior.pattern_detector import PatternDetector
from core.cognition.challenge_logic import ChallengeLogic
from core.cognition.command_router import CommandRouter
from core.cognition.proactive_controller import ProactiveController
from core.memory.lifecycle_manager import LifecycleManager
from core.memory.task_store import TaskStore
from tests.validation.fixtures.multi_source_sync import (
    MockEnergyState,
    MockIdentityContext,
    MockMobileConnector,
    MockSyncDaemon,
)


def _build_runtime() -> tuple[CommandRouter, TaskStore, ProactiveController]:
    lifecycle = LifecycleManager()
    store = TaskStore(lifecycle_manager=lifecycle)
    router = CommandRouter(
        task_store=store,
        lifecycle_manager=lifecycle,
        challenge_logic=ChallengeLogic(),
        config_path="configs/default.yaml",
    )
    proactive = ProactiveController(
        confidence_threshold=0.7,
        daily_limit=100,
        pattern_detector=PatternDetector(),
    )
    return router, store, proactive


def _schedule_intent(*, title: str, intent_id: str) -> dict[str, object]:
    return {
        "intent_id": intent_id,
        "intent_type": "schedule_task",
        "entities": {"task": title},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "confidence_score": 0.95,
    }


def test_proactive_suggestions_remain_advisory_under_sync_load() -> None:
    router, store, proactive = _build_runtime()
    mobile = MockMobileConnector()
    sync = MockSyncDaemon()
    identity = MockIdentityContext(user_id="owner-2", tier="OWNER", authenticated=True)
    energy = MockEnergyState(mode="STRATEGIC", battery_percent=85)

    initial_task_count = len(store.list_tasks(include_archived=True))
    initial_audit_count = len(router.get_audit_events())
    collected_suggestions: list[dict[str, object]] = []

    for index in range(25):
        sync.emit(
            source_id=f"sync-source-{index % 5}",
            sync_type="TASK_SNAPSHOT",
            payload={"external_task_count": index + 1},
            correlation_id=f"sync-proactive-{index}",
            merge_hint={"source_priority": "normal", "version": "v2"},
        )
        mobile.emit(
            action="reminder_ack",
            payload={"identity": identity.user_id, "battery": energy.battery_percent},
            correlation_id=f"mobile-proactive-{index}",
        )
        suggestions = proactive.evaluate(
            {
                "overdue_tasks": 2,
                "scheduled_tasks_today": 11,
                "daily_capacity": 7,
                "goal_alignment_score": 0.4,
                "energy_mode": energy.mode,
            }
        )
        collected_suggestions.extend(suggestions)

        assert len(store.list_tasks(include_archived=True)) == initial_task_count
        assert len(router.get_audit_events()) == initial_audit_count

    assert collected_suggestions
    assert all("message" in suggestion for suggestion in collected_suggestions)
    assert all("task_id" not in suggestion for suggestion in collected_suggestions)

    post_sync_result = router.route(
        _schedule_intent(title="Post-sync routed task", intent_id="intent-proactive-post-sync")
    )
    assert post_sync_result.status == "executed"
    assert post_sync_result.action == "CREATE_TASK"

    assert len(store.list_tasks(include_archived=True)) == initial_task_count + 1
    assert len(router.get_audit_events()) == initial_audit_count + 1

