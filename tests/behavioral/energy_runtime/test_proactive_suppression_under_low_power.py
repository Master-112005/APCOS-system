from __future__ import annotations

from tests.validation.fixtures.energy_runtime_load import build_energy_runtime_harness


def test_proactive_suppression_under_critical_power() -> None:
    harness = build_energy_runtime_harness()
    baseline_audits = harness.router_audit_count()

    harness.sync_burst(count=10, source_prefix="sync-critical")
    harness.set_battery(5)
    result = harness.run_proactive_cycle(
        {
            "overdue_tasks": 3,
            "scheduled_tasks_today": 9,
            "daily_capacity": 5,
            "goal_alignment_score": 0.35,
        }
    )

    assert result["status"] == "skipped"
    assert result["suggestions"] == []
    assert isinstance(result["reason"], str)
    assert "CRITICAL" in result["reason"]
    assert harness.router_audit_count() == baseline_audits

    assert any(
        decision["mode"] == "CRITICAL"
        and decision["execution_type"] == "PROACTIVE"
        and decision["allowed"] is False
        for decision in harness.energy_state.decisions
    )

