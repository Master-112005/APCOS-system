from __future__ import annotations

from tests.validation.fixtures.extended_runtime_stability import (
    run_extended_runtime_simulation,
)


def test_memory_growth_stability_over_extended_runtime() -> None:
    metrics = run_extended_runtime_simulation(10_000)

    growth_start_to_mid_kb = metrics.memory_mid_kb - metrics.memory_start_kb
    growth_mid_to_end_kb = metrics.memory_end_kb - metrics.memory_mid_kb
    growth_total_kb = metrics.memory_end_kb - metrics.memory_start_kb

    assert growth_total_kb <= 12_288.0
    assert growth_mid_to_end_kb <= 6_144.0
    assert growth_mid_to_end_kb <= growth_start_to_mid_kb + 2_048.0
