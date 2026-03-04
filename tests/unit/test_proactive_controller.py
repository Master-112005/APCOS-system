from __future__ import annotations

from datetime import datetime, timezone

from core.cognition.proactive_controller import ProactiveController


def test_proactive_controller_detects_key_patterns() -> None:
    controller = ProactiveController(confidence_threshold=0.7, daily_limit=3)
    now = datetime(2026, 2, 19, 9, 0, tzinfo=timezone.utc)
    context = {
        "overdue_tasks": 2,
        "scheduled_tasks_today": 11,
        "daily_capacity": 8,
        "goal_alignment_score": 0.4,
    }

    suggestions = controller.evaluate(context, now=now, restricted_mode=False)
    assert len(suggestions) == 3
    assert {item["pattern_type"] for item in suggestions} == {
        "missed_task",
        "overloaded_day",
        "goal_deviation",
    }


def test_proactive_controller_respects_daily_limit() -> None:
    controller = ProactiveController(confidence_threshold=0.7, daily_limit=3)
    now = datetime(2026, 2, 19, 9, 0, tzinfo=timezone.utc)
    context = {"overdue_tasks": 3, "scheduled_tasks_today": 15, "goal_alignment_score": 0.1}

    first_batch = controller.evaluate(context, now=now)
    second_batch = controller.evaluate(context, now=now)

    assert len(first_batch) == 3
    assert second_batch == []


def test_proactive_controller_respects_silent_and_restricted_mode() -> None:
    controller = ProactiveController(confidence_threshold=0.6, daily_limit=3)
    context = {"overdue_tasks": 2}
    now = datetime(2026, 2, 19, 10, 0, tzinfo=timezone.utc)

    controller.set_silent_mode(True)
    assert controller.evaluate(context, now=now) == []

    controller.set_silent_mode(False)
    assert controller.evaluate(context, now=now, restricted_mode=True) == []


def test_acceptance_metrics_tracking() -> None:
    controller = ProactiveController()
    now = datetime(2026, 2, 19, 10, 0, tzinfo=timezone.utc)

    controller.record_outcome("accepted", now=now)
    controller.record_outcome("rejected", now=now)
    controller.record_outcome("ignored", now=now, overridden=True)

    metrics = controller.acceptance_metrics()
    assert metrics.accepted == 1
    assert metrics.rejected == 1
    assert metrics.ignored == 1
    assert metrics.overrides == 1


def test_proactive_threshold_recalibrates_from_outcomes() -> None:
    controller = ProactiveController(confidence_threshold=0.7)
    now = datetime(2026, 2, 19, 11, 0, tzinfo=timezone.utc)

    for _ in range(8):
        controller.record_outcome("accepted", now=now)
    controller.record_outcome("rejected", now=now)
    controller.record_outcome("ignored", now=now)

    assert controller.confidence_threshold == 0.5
