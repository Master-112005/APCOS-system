"""Deterministic scoring and keying for proactive suggestions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from core.behavior.pattern_detector import PatternResult


@dataclass(frozen=True)
class ScoredSuggestion:
    """Proactive suggestion candidate with deterministic score and stable key."""

    pattern: PatternResult
    score: float
    key: str


class SuggestionScorer:
    """
    Score and rank proactive suggestion candidates deterministically.

    This module is pure computation: no state mutation, no clock usage, and
    no randomization.
    """

    _PATTERN_WEIGHT: dict[str, float] = {
        "goal_deviation": 3.0,
        "overloaded_day": 2.0,
        "missed_task": 1.0,
    }

    def rank(
        self,
        patterns: Iterable[PatternResult],
        context: Mapping[str, Any],
    ) -> list[ScoredSuggestion]:
        """Return descending deterministic ranking for pattern candidates."""
        task_id = self._extract_task_id(context)
        ranked: list[ScoredSuggestion] = []

        for pattern in patterns:
            weight = self._PATTERN_WEIGHT.get(pattern.pattern_type, 0.5)
            score = (float(pattern.confidence) * 100.0) + weight
            key = self._build_key(pattern.pattern_type, task_id, pattern.details)
            ranked.append(
                ScoredSuggestion(
                    pattern=pattern,
                    score=score,
                    key=key,
                )
            )

        ranked.sort(
            key=lambda item: (
                -item.score,
                item.pattern.pattern_type,
                item.key,
            )
        )
        return ranked

    @staticmethod
    def _extract_task_id(context: Mapping[str, Any]) -> str:
        task_id = context.get("task_id")
        if task_id is None:
            return "global"
        return str(task_id)

    @staticmethod
    def _build_key(
        pattern_type: str,
        task_id: str,
        details: Mapping[str, Any],
    ) -> str:
        anchor = "global"
        if "overdue_tasks" in details:
            anchor = f"overdue:{int(details['overdue_tasks'])}"
        elif "scheduled_tasks_today" in details and "daily_capacity" in details:
            anchor = f"load:{int(details['scheduled_tasks_today'])}:{int(details['daily_capacity'])}"
        elif "goal_alignment_score" in details:
            anchor = f"align:{float(details['goal_alignment_score']):.2f}"

        return f"{pattern_type}|task:{task_id}|{anchor}"

