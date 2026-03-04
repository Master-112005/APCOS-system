from __future__ import annotations

from collections.abc import Iterator
from typing import Callable

from voice.wake_word import WakeWordDetector


def _event_source(events: list[str | None]) -> Callable[[], str | None]:
    iterator: Iterator[str | None] = iter(events)

    def _read() -> str | None:
        try:
            return next(iterator)
        except StopIteration:
            return None

    return _read


def test_wake_word_detector_matches_trigger_phrase() -> None:
    detector = WakeWordDetector(event_source=_event_source(["hello", "hey apcos now"]))
    assert detector.listen() is False
    assert detector.listen() is True


def test_wake_word_detector_handles_missing_events() -> None:
    detector = WakeWordDetector(event_source=_event_source([None]))
    assert detector.listen() is False
