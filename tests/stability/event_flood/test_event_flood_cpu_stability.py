from __future__ import annotations

import statistics

from tests.validation.fixtures.event_flood_stability import (
    build_event_flood_stability_harness,
)


def test_event_flood_cpu_stability() -> None:
    batch_durations_ms: list[float] = []
    aggregate_latencies_ms: list[float] = []

    for batch in range(5):
        harness = build_event_flood_stability_harness()
        metrics = harness.run_flood(iterations=200, start_index=batch * 2000)
        batch_durations_ms.append(metrics.total_elapsed_ms)
        aggregate_latencies_ms.extend(metrics.latency_samples_ms)

        assert metrics.total_published == 800
        assert metrics.processed_events == 800
        assert metrics.state_updates == 800

    duration_mean = statistics.fmean(batch_durations_ms)
    duration_variation = max(batch_durations_ms) - min(batch_durations_ms)
    latency_mean = statistics.fmean(aggregate_latencies_ms)
    p95_latency = sorted(aggregate_latencies_ms)[int(len(aggregate_latencies_ms) * 0.95) - 1]

    assert duration_mean < 2_000.0
    assert duration_variation <= max(30.0, duration_mean * 1.5)
    assert latency_mean < 2.0
    assert p95_latency <= (latency_mean * 8.0) + 2.0
