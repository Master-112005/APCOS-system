"""Acceptance/rejection tracking for proactive calibration metrics."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Literal

Outcome = Literal["accepted", "rejected", "ignored"]


@dataclass(frozen=True)
class AcceptanceMetrics:
    """Computed acceptance metrics."""

    accepted: int
    rejected: int
    ignored: int
    overrides: int
    acceptance_rate: float


class AcceptanceTracker:
    """Track suggestion outcomes and override frequency over time."""

    def __init__(self) -> None:
        self._daily_stats = defaultdict(
            lambda: {"accepted": 0, "rejected": 0, "ignored": 0, "overrides": 0}
        )

    def record(
        self,
        outcome: Outcome,
        *,
        when: datetime | None = None,
        overridden: bool = False,
    ) -> None:
        """Record a single proactive outcome event."""
        if outcome not in {"accepted", "rejected", "ignored"}:
            raise ValueError(f"Unsupported outcome: {outcome}")
        current = when or datetime.now(timezone.utc)
        bucket = self._daily_stats[current.date()]
        bucket[outcome] += 1
        if overridden:
            bucket["overrides"] += 1

    def daily_metrics(self, day: date | None = None) -> AcceptanceMetrics:
        """Return metrics for a single day."""
        selected = day or datetime.now(timezone.utc).date()
        stats = self._daily_stats[selected]
        return self._compute(stats)

    def total_metrics(self) -> AcceptanceMetrics:
        """Return aggregate metrics over all recorded days."""
        total = {"accepted": 0, "rejected": 0, "ignored": 0, "overrides": 0}
        for stats in self._daily_stats.values():
            for key in total:
                total[key] += stats[key]
        return self._compute(total)

    @staticmethod
    def _compute(raw: dict[str, int]) -> AcceptanceMetrics:
        attempts = raw["accepted"] + raw["rejected"] + raw["ignored"]
        if attempts == 0:
            rate = 0.0
        else:
            rate = raw["accepted"] / attempts
        return AcceptanceMetrics(
            accepted=raw["accepted"],
            rejected=raw["rejected"],
            ignored=raw["ignored"],
            overrides=raw["overrides"],
            acceptance_rate=rate,
        )
