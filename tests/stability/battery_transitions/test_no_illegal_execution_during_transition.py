from __future__ import annotations

from tests.validation.fixtures.battery_transition_stability import (
    build_battery_transition_harness,
)


def test_no_illegal_execution_during_silent_transition() -> None:
    harness = build_battery_transition_harness()
    runtime = harness.runtime
    baseline_audits = runtime.router_audit_count()

    runtime.sync_burst(count=10, source_prefix="transition-guard")
    runtime.set_battery(10)

    heavy_reasoning = runtime.run_reasoning("Design a deep multi-week strategy with branches.")
    proactive = runtime.run_proactive_cycle(
        {
            "overdue_tasks": 4,
            "scheduled_tasks_today": 10,
            "daily_capacity": 4,
            "goal_alignment_score": 0.2,
        }
    )
    voice_response = harness.run_voice_check(transcript="status check")
    heavy_voice_response = harness.run_voice_check(transcript="/strategy organize my entire month")

    assert heavy_reasoning["allowed"] is False
    assert heavy_reasoning["mode"] == "CRITICAL"
    assert "blocked_critical" in str(heavy_reasoning["reason"]).lower()

    assert proactive["status"] == "skipped"
    assert "critical" in str(proactive["reason"]).lower()

    assert "voice command acknowledged" in voice_response.lower()
    assert "energy gate:" in heavy_voice_response.lower()
    assert "blocked_critical" in heavy_voice_response.lower()

    assert runtime.router_audit_count() == baseline_audits
