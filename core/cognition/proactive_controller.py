"""Rule-based proactive suggestion controller."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import date, datetime, timezone
from typing import Any, Mapping
import uuid

from core.behavior.acceptance_tracker import AcceptanceMetrics, AcceptanceTracker, Outcome
from core.behavior.calibration_engine import CalibrationEngine
from core.behavior.pattern_detector import PatternDetector, PatternResult
from core.behavior.suggestion_scorer import SuggestionScorer


class ProactiveController:
    """
    Control proactive suggestions under deterministic guardrails.

    Guardrails:
    - daily suggestion limit
    - confidence threshold
    - silent/restricted mode compliance
    - recent suggestion window limit
    - repeated suggestion suppression
    - deterministic cooldown by evaluation sequence
    """

    def __init__(
        self,
        *,
        confidence_threshold: float = 0.7,
        daily_limit: int = 3,
        recent_suggestion_window: int = 10,
        max_suggestions_per_window: int = 3,
        repetition_cooldown_steps: int = 4,
        pattern_detector: PatternDetector | None = None,
        suggestion_scorer: SuggestionScorer | None = None,
        acceptance_tracker: AcceptanceTracker | None = None,
        calibration_engine: CalibrationEngine | None = None,
    ) -> None:
        if daily_limit < 1:
            raise ValueError("daily_limit must be >= 1")
        if confidence_threshold < 0.0 or confidence_threshold > 1.0:
            raise ValueError("confidence_threshold must be between 0 and 1")

        if recent_suggestion_window < 1:
            raise ValueError("recent_suggestion_window must be >= 1")
        if max_suggestions_per_window < 1:
            raise ValueError("max_suggestions_per_window must be >= 1")
        if repetition_cooldown_steps < 1:
            raise ValueError("repetition_cooldown_steps must be >= 1")

        self._confidence_threshold = confidence_threshold
        self._daily_limit = daily_limit
        self._recent_suggestion_window = recent_suggestion_window
        self._max_suggestions_per_window = max_suggestions_per_window
        self._repetition_cooldown_steps = repetition_cooldown_steps
        self._pattern_detector = pattern_detector or PatternDetector()
        self._suggestion_scorer = suggestion_scorer or SuggestionScorer()
        self._acceptance_tracker = acceptance_tracker or AcceptanceTracker()
        self._calibration_engine = calibration_engine or CalibrationEngine()
        self._silent_mode = False
        self._daily_suggestion_count = defaultdict(int)
        self._evaluation_sequence = 0
        self._recent_suggestion_steps: deque[int] = deque()
        self._last_suggestion_step_by_key: dict[str, int] = {}

    @property
    def confidence_threshold(self) -> float:
        """Current proactive confidence threshold."""
        return self._confidence_threshold

    def set_silent_mode(self, enabled: bool) -> None:
        """Enable/disable silent mode."""
        self._silent_mode = bool(enabled)

    def evaluate(
        self,
        context: Mapping[str, Any],
        *,
        now: datetime | None = None,
        restricted_mode: bool = False,
    ) -> list[dict[str, Any]]:
        """Evaluate context and return zero or more proactive suggestions."""
        self._evaluation_sequence += 1
        sequence = self._evaluation_sequence
        current = now or datetime.now(timezone.utc)
        day = current.date()

        if self._silent_mode or restricted_mode:
            return []
        if self.remaining_budget(day) == 0:
            return []

        suggestions: list[dict[str, Any]] = []
        patterns = self._pattern_detector.detect(dict(context))
        ranked = self._suggestion_scorer.rank(patterns, context)

        self._evict_old_window_entries(sequence)
        for candidate in ranked:
            pattern = candidate.pattern
            if pattern.confidence < self._confidence_threshold:
                continue
            if self.remaining_budget(day) == 0:
                break
            if self._window_limit_reached():
                break
            if self._is_repeat_suppressed(candidate.key, sequence):
                continue

            suggestion = self._build_suggestion(pattern, current)
            suggestion["suggestion_key"] = candidate.key
            suggestions.append(suggestion)
            self._daily_suggestion_count[day] += 1
            self._recent_suggestion_steps.append(sequence)
            self._last_suggestion_step_by_key[candidate.key] = sequence

        return suggestions

    def record_outcome(
        self,
        outcome: Outcome,
        *,
        now: datetime | None = None,
        overridden: bool = False,
    ) -> None:
        """Record whether a suggestion was accepted/rejected/ignored."""
        self._acceptance_tracker.record(outcome, when=now, overridden=overridden)
        self.recalibrate_threshold()

    def acceptance_metrics(self) -> AcceptanceMetrics:
        """Return aggregate proactive acceptance metrics."""
        return self._acceptance_tracker.total_metrics()

    def recalibrate_threshold(self) -> float:
        """
        Recompute proactive confidence threshold from acceptance metrics.

        The calibration engine is pure and only returns a bounded value.
        The controller applies that value to its local threshold.
        """
        metrics = self._acceptance_tracker.total_metrics()
        updated = self._calibration_engine.update_threshold(self._confidence_threshold, metrics)
        self._confidence_threshold = updated
        return updated

    def remaining_budget(self, day: date | None = None) -> int:
        """Return remaining suggestion budget for a given day."""
        selected_day = day or datetime.now(timezone.utc).date()
        used = self._daily_suggestion_count[selected_day]
        return max(0, self._daily_limit - used)

    def _evict_old_window_entries(self, sequence: int) -> None:
        min_allowed = sequence - self._recent_suggestion_window + 1
        while self._recent_suggestion_steps and self._recent_suggestion_steps[0] < min_allowed:
            self._recent_suggestion_steps.popleft()

    def _window_limit_reached(self) -> bool:
        return len(self._recent_suggestion_steps) >= self._max_suggestions_per_window

    def _is_repeat_suppressed(self, key: str, sequence: int) -> bool:
        previous = self._last_suggestion_step_by_key.get(key)
        if previous is None:
            return False
        return (sequence - previous) <= self._repetition_cooldown_steps

    @staticmethod
    def _build_suggestion(pattern: PatternResult, current: datetime) -> dict[str, Any]:
        suggestion_templates = {
            "missed_task": "You missed planned work. Rebalance today's priorities?",
            "overloaded_day": "Today's plan is overloaded. Want a lighter schedule?",
            "goal_deviation": "Current actions are drifting from your goal. Realign now?",
        }
        return {
            "suggestion_id": str(uuid.uuid4()),
            "pattern_type": pattern.pattern_type,
            "message": suggestion_templates.get(
                pattern.pattern_type, "A proactive adjustment may help your day."
            ),
            "confidence": pattern.confidence,
            "details": pattern.details,
            "timestamp": current.isoformat(),
        }
