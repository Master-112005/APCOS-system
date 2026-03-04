from __future__ import annotations

from core.cognition.proactive_controller import ProactiveController


def test_repeat_suppression_blocks_immediate_duplicate() -> None:
    controller = ProactiveController(
        confidence_threshold=0.7,
        daily_limit=20,
        recent_suggestion_window=20,
        max_suggestions_per_window=20,
        repetition_cooldown_steps=3,
    )
    context = {
        "task_id": 101,
        "overdue_tasks": 2,
    }

    first = controller.evaluate(context)
    second = controller.evaluate(context)

    assert len(first) == 1
    assert second == []


def test_repeat_suppression_key_changes_allow_new_suggestion() -> None:
    controller = ProactiveController(
        confidence_threshold=0.7,
        daily_limit=20,
        recent_suggestion_window=20,
        max_suggestions_per_window=20,
        repetition_cooldown_steps=3,
    )

    first = controller.evaluate({"task_id": 101, "overdue_tasks": 2})
    changed = controller.evaluate({"task_id": 101, "overdue_tasks": 3})

    assert len(first) == 1
    assert len(changed) == 1
    assert first[0]["suggestion_key"] != changed[0]["suggestion_key"]

