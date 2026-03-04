from __future__ import annotations

import gc
import threading
import time

from tests.validation.fixtures.wakeword_stability import (
    build_wakeword_stability_harness,
)


def test_no_thread_buildup_across_1000_cycles() -> None:
    start_thread_count = threading.active_count()
    harness = build_wakeword_stability_harness(transcript="thread stability check")

    harness.run_cycles(1000)

    time.sleep(0.01)
    gc.collect()
    end_thread_count = threading.active_count()

    assert end_thread_count - start_thread_count <= 1
