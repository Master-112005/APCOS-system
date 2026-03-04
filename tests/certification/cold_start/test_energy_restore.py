from __future__ import annotations

from tests.validation.fixtures.energy_runtime_load import build_energy_runtime_harness


def test_energy_mode_restores_reduced_after_restart() -> None:
    runtime_a = build_energy_runtime_harness()
    runtime_a.set_battery(30)
    report_a = runtime_a.run_reasoning("Check reduced mode before restart")
    saved_battery = runtime_a.energy_state.battery_percent

    runtime_b = build_energy_runtime_harness()
    runtime_b.set_battery(saved_battery)
    report_b = runtime_b.run_reasoning("Check reduced mode after restart")

    assert report_a["mode"] == "REDUCED"
    assert report_b["mode"] == "REDUCED"
    assert report_a["allowed"] is True
    assert report_b["allowed"] is True
    assert report_a["downgraded"] is True
    assert report_b["downgraded"] is True
