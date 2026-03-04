"""Microphone health checks for APCOS hardware abstraction layer."""

from __future__ import annotations

from typing import Callable


AudioReader = Callable[[], bytes]
HealthProbe = Callable[[], bool]


class MicrophoneHealth:
    """Detect microphone availability and no-input failure conditions."""

    def __init__(
        self,
        *,
        audio_reader: AudioReader | None = None,
        health_probe: HealthProbe | None = None,
        max_no_input_checks: int = 3,
    ) -> None:
        if max_no_input_checks < 1:
            raise ValueError("max_no_input_checks must be >= 1")
        self._audio_reader = audio_reader
        self._health_probe = health_probe
        self._max_no_input_checks = int(max_no_input_checks)
        self._consecutive_no_input = 0
        self._last_error: str | None = None

    def is_operational(self) -> bool:
        """Run one health check cycle and return microphone status."""
        if self._health_probe is not None:
            try:
                if not bool(self._health_probe()):
                    self._last_error = "MICROPHONE_UNAVAILABLE"
                    return False
            except Exception:
                self._last_error = "MICROPHONE_PROBE_FAILURE"
                return False

        if self._audio_reader is None:
            self._last_error = None
            return True

        try:
            chunk = self._audio_reader() or b""
        except Exception:
            self._last_error = "MICROPHONE_READ_FAILURE"
            return False

        if chunk:
            self._consecutive_no_input = 0
            self._last_error = None
            return True

        self._consecutive_no_input += 1
        if self._consecutive_no_input >= self._max_no_input_checks:
            self._last_error = "MICROPHONE_NO_INPUT"
            return False
        self._last_error = None
        return True

    def last_error(self) -> str | None:
        """Return the last health-check error code, if any."""
        return self._last_error

