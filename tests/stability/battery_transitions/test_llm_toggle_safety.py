from __future__ import annotations

from tests.validation.fixtures.battery_transition_stability import (
    build_battery_transition_harness,
)


def test_llm_toggle_safety_downgrade_before_disable_and_restore() -> None:
    harness = build_battery_transition_harness()
    runtime = harness.runtime

    runtime.set_battery(60)
    strategic = runtime.run_reasoning("Plan quarterly roadmap.")

    runtime.set_battery(30)
    reduced = runtime.run_reasoning("Plan quarterly roadmap.")

    runtime.set_battery(10)
    silent = runtime.run_reasoning("Plan quarterly roadmap.")

    runtime.set_battery(70)
    restored = runtime.run_reasoning("Plan quarterly roadmap.")

    assert strategic["allowed"] is True
    assert strategic["downgraded"] is False
    assert strategic["mode"] == "NORMAL"

    assert reduced["allowed"] is True
    assert reduced["downgraded"] is True
    assert reduced["mode"] == "REDUCED"

    assert silent["allowed"] is False
    assert silent["downgraded"] is False
    assert silent["mode"] == "CRITICAL"
    assert "blocked_critical" in str(silent["reason"]).lower()

    assert restored["allowed"] is True
    assert restored["downgraded"] is False
    assert restored["mode"] == "NORMAL"

    llm_decisions = [
        decision
        for decision in runtime.energy_state.decisions
        if decision.get("execution_type") == "LLM"
    ]
    assert len(llm_decisions) >= 4
    recent = llm_decisions[-4:]

    assert recent[0]["mode"] == "NORMAL" and recent[0]["allowed"] is True
    assert recent[1]["mode"] == "REDUCED" and recent[1]["allowed"] is True
    assert recent[2]["mode"] == "CRITICAL" and recent[2]["allowed"] is False
    assert recent[3]["mode"] == "NORMAL" and recent[3]["allowed"] is True
