from __future__ import annotations

from tests.validation.fixtures.sync_burst_stability import (
    build_sync_burst_stability_harness,
)


def test_event_bus_queue_integrity_under_sync_burst() -> None:
    harness = build_sync_burst_stability_harness(
        max_queue_size=512,
        drain_every=12,
        drain_batch_size=9,
    )
    metrics = harness.run_burst(iterations=1000, mobile_every=5)
    expected_mobile = 200
    expected_total = 1200

    assert metrics.sync_sent == 1000
    assert metrics.mobile_sent == expected_mobile
    assert metrics.total_sent == expected_total
    assert metrics.processed_count == expected_total

    assert metrics.max_queue_depth <= 512
    assert metrics.overflow_detected is False
    assert metrics.pending_queue == 0
    assert metrics.duplicate_count == 0

    assert len(harness.bridge.messages) == expected_total
    assert len({msg["correlation_id"] for msg in harness.bridge.messages}) == expected_total
