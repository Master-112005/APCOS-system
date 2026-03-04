"""Fixtures for long-run battery transition stability validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tests.validation.fixtures.energy_runtime_load import (
    MockTTS,
    build_energy_runtime_harness,
)


@dataclass(frozen=True)
class BatteryStageResult:
    """One deterministic battery-stage outcome snapshot."""

    battery_percent: int
    mode: str
    reasoning_allowed: bool
    reasoning_downgraded: bool
    reasoning_reason: str | None
    voice_allowed: bool
    voice_response: str
    proactive_status: str
    proactive_reason: str | None


class BatteryTransitionHarness:
    """Wrapper harness for full battery lifecycle stability scenarios."""

    CYCLE_POINTS = (60, 30, 10, 5, 70)

    def __init__(self) -> None:
        self.runtime = build_energy_runtime_harness()
        self.tts = MockTTS()

    def run_stage(self, *, battery_percent: int, stage_name: str) -> BatteryStageResult:
        self.runtime.sync_burst(count=6, source_prefix=f"battery-{stage_name}")
        self.runtime.set_battery(battery_percent)

        reasoning = self.runtime.run_reasoning("Plan weekly priorities and next milestones.")
        proactive = self.runtime.run_proactive_cycle(
            {
                "overdue_tasks": 2,
                "scheduled_tasks_today": 6,
                "daily_capacity": 5,
                "goal_alignment_score": 0.6,
            }
        )
        voice_response = self.run_voice_check(transcript="status check")
        _ = self.tts.speak(voice_response)

        return BatteryStageResult(
            battery_percent=battery_percent,
            mode=str(reasoning.get("mode", "")),
            reasoning_allowed=bool(reasoning.get("allowed", False)),
            reasoning_downgraded=bool(reasoning.get("downgraded", False)),
            reasoning_reason=self._none_if_empty(reasoning.get("reason")),
            voice_allowed="voice command acknowledged" in voice_response.lower(),
            voice_response=voice_response,
            proactive_status=str(proactive.get("status", "")),
            proactive_reason=self._none_if_empty(proactive.get("reason")),
        )

    def run_cycle(self) -> list[BatteryStageResult]:
        reports: list[BatteryStageResult] = []
        for index, battery in enumerate(self.CYCLE_POINTS):
            reports.append(self.run_stage(battery_percent=battery, stage_name=f"stage-{index}"))
        return reports

    def run_voice_check(self, *, transcript: str) -> str:
        session = self.runtime.build_voice_session(transcript=transcript)
        response = session.run_once()
        return str(response or "")

    @staticmethod
    def _none_if_empty(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text if text else None


def build_battery_transition_harness() -> BatteryTransitionHarness:
    """Factory for deterministic battery transition stability validation."""
    return BatteryTransitionHarness()
