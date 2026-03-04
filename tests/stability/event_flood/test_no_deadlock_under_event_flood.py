from __future__ import annotations

import time

from tests.validation.fixtures.event_flood_stability import (
    build_event_flood_stability_harness,
)


def test_no_deadlock_under_event_flood() -> None:
    harness = build_event_flood_stability_harness()

    start = time.perf_counter()
    metrics = harness.run_flood(iterations=1000)
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    expected_total = 1000 * 4
    assert metrics.total_published == expected_total
    assert metrics.processed_events == expected_total
    assert metrics.state_updates == expected_total
    assert elapsed_ms < 10_000.0
