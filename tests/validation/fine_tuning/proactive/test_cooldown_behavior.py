from __future__ import annotations

from core.cognition.proactive_controller import ProactiveController


def test_cooldown_uses_deterministic_sequence_steps() -> None:
    controller = ProactiveController(
        confidence_threshold=0.7,
        daily_limit=20,
        recent_suggestion_window=20,
        max_suggestions_per_window=20,
        repetition_cooldown_steps=2,
    )
    context = {"task_id": 501, "overdue_tasks": 2}

    first = controller.evaluate(context)
    second = controller.evaluate(context)
    third = controller.evaluate(context)
    fourth = controller.evaluate(context)

    assert len(first) == 1
    assert second == []
    assert third == []
    assert len(fourth) == 1
    assert first[0]["suggestion_key"] == fourth[0]["suggestion_key"]


def test_cooldown_behavior_is_not_wall_clock_dependent() -> None:
    controller = ProactiveController(
        confidence_threshold=0.7,
        daily_limit=20,
        recent_suggestion_window=20,
        max_suggestions_per_window=20,
        repetition_cooldown_steps=1,
    )
    context = {"task_id": 777, "overdue_tasks": 2}

    first = controller.evaluate(context)
    second = controller.evaluate(context)
    third = controller.evaluate(context)

    assert len(first) == 1
    assert second == []
    assert len(third) == 1

