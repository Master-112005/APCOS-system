from __future__ import annotations

from tests.validation.fixtures.extended_runtime_stability import (
    run_extended_runtime_simulation,
)


def test_thread_count_stability_over_extended_runtime() -> None:
    metrics = run_extended_runtime_simulation(10_000)

    start_to_mid_delta = metrics.thread_mid_count - metrics.thread_start_count
    start_to_end_delta = metrics.thread_end_count - metrics.thread_start_count

    assert start_to_mid_delta <= 1
    assert start_to_end_delta <= 1
