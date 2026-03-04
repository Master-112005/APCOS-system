"""Wake-word detection stub for APCOS voice layer."""

from __future__ import annotations

from typing import Callable


class WakeWordDetector:
    """Deterministic wake-word detector using injected text event source."""

    def __init__(
        self,
        *,
        trigger_phrase: str = "hey apcos",
        event_source: Callable[[], str | None] | None = None,
    ) -> None:
        normalized = " ".join(trigger_phrase.lower().strip().split())
        if not normalized:
            raise ValueError("trigger_phrase must not be empty")
        self._trigger_phrase = normalized
        self._event_source = event_source or (lambda: None)

    def listen(self) -> bool:
        """
        Return True when the incoming event contains the trigger phrase.

        This method is non-blocking and deterministic in the Stage 6 stub.
        """
        event = self._event_source()
        if event is None:
            return False
        normalized = " ".join(str(event).lower().strip().split())
        return self._trigger_phrase in normalized
