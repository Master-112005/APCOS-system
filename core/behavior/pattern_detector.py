"""Rule-based behavior pattern detection for proactive suggestions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PatternResult:
    """Detected pattern with confidence and supporting details."""

    pattern_type: str
    confidence: float
    details: dict[str, Any]


class PatternDetector:
    """Detect missed tasks, overload, and goal deviation patterns."""

    def __init__(
        self,
        *,
        overload_threshold: int = 8,
        goal_deviation_threshold: float = 0.6,
    ) -> None:
        self._overload_threshold = overload_threshold
        self._goal_deviation_threshold = goal_deviation_threshold

    def detect(self, context: dict[str, Any]) -> list[PatternResult]:
        """Return list of currently detected patterns."""
        results: list[PatternResult] = []

        overdue_tasks = int(context.get("overdue_tasks", 0))
        if overdue_tasks > 0:
            results.append(
                PatternResult(
                    pattern_type="missed_task",
                    confidence=min(1.0, 0.6 + (overdue_tasks * 0.1)),
                    details={"overdue_tasks": overdue_tasks},
                )
            )

        scheduled = int(context.get("scheduled_tasks_today", 0))
        capacity = int(context.get("daily_capacity", self._overload_threshold))
        hard_capacity = max(self._overload_threshold, capacity)
        if scheduled > hard_capacity:
            overflow = scheduled - hard_capacity
            results.append(
                PatternResult(
                    pattern_type="overloaded_day",
                    confidence=min(1.0, 0.65 + (overflow * 0.05)),
                    details={"scheduled_tasks_today": scheduled, "daily_capacity": hard_capacity},
                )
            )

        goal_alignment = float(context.get("goal_alignment_score", 1.0))
        if goal_alignment < self._goal_deviation_threshold:
            deviation = self._goal_deviation_threshold - goal_alignment
            results.append(
                PatternResult(
                    pattern_type="goal_deviation",
                    confidence=min(1.0, 0.6 + deviation),
                    details={"goal_alignment_score": goal_alignment},
                )
            )

        return results
