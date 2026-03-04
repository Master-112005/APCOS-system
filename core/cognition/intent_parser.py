"""Pure text-to-intent parser for deterministic command handling."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
import re
from typing import Any

SCHEDULE_PATTERN = re.compile(
    r"^\s*schedule\s+(?P<task>.+?)\s+tomorrow(?:\s+at\s+(?P<clock>\d{1,2}(?::\d{2})?\s*(?:am|pm)?))?\s*$",
    re.IGNORECASE,
)
MARK_COMPLETED_PATTERN = re.compile(
    r"^\s*mark\s+(?P<task>.+?)\s+completed\s*$",
    re.IGNORECASE,
)
CANCEL_PATTERN = re.compile(
    r"^\s*cancel(?:\s+task)?(?:\s+(?P<task>.+))?\s*$",
    re.IGNORECASE,
)


def parse_intent(text: str, *, now: datetime | None = None) -> dict[str, Any]:
    """
    Parse raw transcript text into a normalized intent object.

    Return shape:
    {
        "intent_type": str,
        "entities": dict[str, Any],
        "timestamp": str,
        "confidence_score": float
    }
    """
    current = now or datetime.now(timezone.utc)
    normalized = " ".join(text.strip().split())
    if not normalized:
        return _intent("unknown", {}, current, confidence=0.0)

    schedule_match = SCHEDULE_PATTERN.match(normalized)
    if schedule_match:
        task_name = schedule_match.group("task").strip()
        due_at = _parse_tomorrow_time(current, schedule_match.group("clock"))
        return _intent(
            "schedule_task",
            {
                "task": task_name,
                "due_at": due_at,
            },
            current,
            confidence=0.93,
        )

    completed_match = MARK_COMPLETED_PATTERN.match(normalized)
    if completed_match:
        task_name = completed_match.group("task").strip()
        return _intent(
            "mark_completed",
            {"task": task_name},
            current,
            confidence=0.96,
        )

    cancel_match = CANCEL_PATTERN.match(normalized)
    if cancel_match:
        task_name = cancel_match.group("task")
        entities: dict[str, Any] = {}
        if task_name:
            entities["task"] = task_name.strip()
        return _intent("cancel_task", entities, current, confidence=0.91)

    return _intent("unknown", {"raw_text": normalized}, current, confidence=0.25)


def _parse_tomorrow_time(current: datetime, clock_text: str | None) -> str:
    """
    Parse optional clock time and convert to ISO timestamp for tomorrow.

    If no time is provided, defaults to 09:00.
    """
    selected_time = time(hour=9, minute=0)
    if clock_text:
        selected_time = _parse_clock(clock_text.strip().lower())

    tomorrow = (current + timedelta(days=1)).date()
    due_at = datetime.combine(tomorrow, selected_time, tzinfo=current.tzinfo or timezone.utc)
    return due_at.isoformat()


def _parse_clock(clock_text: str) -> time:
    match = re.match(
        r"^(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?(?:\s*(?P<ampm>am|pm))?$",
        clock_text,
    )
    if not match:
        raise ValueError(f"Invalid clock string: {clock_text!r}")

    hour = int(match.group("hour"))
    minute = int(match.group("minute") or "0")
    ampm = match.group("ampm")

    if ampm:
        if hour < 1 or hour > 12:
            raise ValueError(f"Invalid hour for 12h format: {hour}")
        if ampm == "am":
            hour = 0 if hour == 12 else hour
        else:
            hour = 12 if hour == 12 else hour + 12
    elif hour > 23:
        raise ValueError(f"Invalid hour for 24h format: {hour}")

    if minute < 0 or minute > 59:
        raise ValueError(f"Invalid minute: {minute}")

    return time(hour=hour, minute=minute)


def _intent(
    intent_type: str,
    entities: dict[str, Any],
    current: datetime,
    *,
    confidence: float,
) -> dict[str, Any]:
    return {
        "intent_type": intent_type,
        "entities": entities,
        "timestamp": current.isoformat(),
        "confidence_score": float(confidence),
    }
