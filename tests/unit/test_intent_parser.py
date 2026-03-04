from __future__ import annotations

from datetime import datetime, timezone

from core.cognition.intent_parser import parse_intent


def test_schedule_intent_parses_expected_fields() -> None:
    now = datetime(2026, 2, 19, 8, 30, tzinfo=timezone.utc)
    result = parse_intent("Schedule meeting tomorrow at 10", now=now)

    assert result["intent_type"] == "schedule_task"
    assert result["entities"]["task"] == "meeting"
    assert result["entities"]["due_at"].startswith("2026-02-20T10:00:00")
    assert result["confidence_score"] > 0.9


def test_mark_completed_intent() -> None:
    now = datetime(2026, 2, 19, 8, 30, tzinfo=timezone.utc)
    result = parse_intent("Mark workout completed", now=now)

    assert result["intent_type"] == "mark_completed"
    assert result["entities"]["task"] == "workout"
    assert result["confidence_score"] > 0.9


def test_cancel_intent() -> None:
    now = datetime(2026, 2, 19, 8, 30, tzinfo=timezone.utc)
    result = parse_intent("Cancel task", now=now)

    assert result["intent_type"] == "cancel_task"
    assert result["entities"] == {}


def test_unknown_intent() -> None:
    now = datetime(2026, 2, 19, 8, 30, tzinfo=timezone.utc)
    result = parse_intent("This is not a command", now=now)

    assert result["intent_type"] == "unknown"
    assert result["confidence_score"] < 0.5
