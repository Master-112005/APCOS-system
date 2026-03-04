from __future__ import annotations

from core.behavior.thread_limiter import ThreadLimiter


def test_thread_limiter_enforces_max_slots() -> None:
    limiter = ThreadLimiter(max_threads=2)

    assert limiter.acquire_slot(timeout=0.01) is True
    assert limiter.acquire_slot(timeout=0.01) is True
    assert limiter.available_slots() == 0
    assert limiter.acquire_slot(timeout=0.01) is False

    limiter.release_slot()
    assert limiter.available_slots() == 1
    assert limiter.acquire_slot(timeout=0.01) is True


def test_thread_limiter_release_is_safe_when_no_slots_acquired() -> None:
    limiter = ThreadLimiter(max_threads=1)
    limiter.release_slot()
    assert limiter.available_slots() == 1
