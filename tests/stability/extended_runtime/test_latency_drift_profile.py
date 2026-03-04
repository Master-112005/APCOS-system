from __future__ import annotations

import statistics

from tests.validation.fixtures.extended_runtime_stability import (
    run_extended_runtime_simulation,
)


def test_latency_drift_profile_is_stable() -> None:
    metrics = run_extended_runtime_simulation(10_000)
    latencies = list(metrics.latency_samples_ms)

    assert len(latencies) == 10_000
    assert all(value >= 0.0 for value in latencies)

    early_avg = statistics.fmean(latencies[:2000])
    late_avg = statistics.fmean(latencies[-2000:])
    p95 = sorted(latencies)[int(len(latencies) * 0.95) - 1]

    window_means = [
        statistics.fmean(latencies[index : index + 1000])
        for index in range(0, len(latencies), 1000)
    ]

    assert late_avg <= (early_avg * 2.0) + 1.0
    assert p95 <= (metrics.average_cycle_latency_ms * 8.0) + 2.0
    assert (max(window_means) - min(window_means)) <= max(3.0, early_avg * 4.0)
