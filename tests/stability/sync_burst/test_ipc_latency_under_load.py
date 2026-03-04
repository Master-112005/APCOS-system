from __future__ import annotations

import statistics

from tests.validation.fixtures.sync_burst_stability import (
    build_sync_burst_stability_harness,
)


def test_ipc_latency_under_load_stays_stable() -> None:
    harness = build_sync_burst_stability_harness(
        max_queue_size=512,
        drain_every=10,
        drain_batch_size=7,
    )
    metrics = harness.run_burst(iterations=800, mobile_every=5)

    latencies = list(metrics.latency_samples_ms)
    assert len(latencies) == metrics.total_sent
    assert all(value >= 0.0 for value in latencies)

    latency_variation = metrics.max_latency_ms - metrics.min_latency_ms
    p95 = sorted(latencies)[int(len(latencies) * 0.95) - 1]
    assert metrics.average_latency_ms < 2.0
    assert latency_variation <= 25.0
    assert metrics.max_latency_ms <= (metrics.average_latency_ms * 6.0) + 4.0
    assert p95 <= (metrics.average_latency_ms * 4.0) + 2.0

    # Deterministic aggregate sanity checks.
    assert statistics.fmean(latencies) >= metrics.min_latency_ms
    assert statistics.fmean(latencies) <= metrics.max_latency_ms

    assert metrics.total_elapsed_ms < 10_000.0
