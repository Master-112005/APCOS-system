from __future__ import annotations

from services.hardware.microphone_health import MicrophoneHealth


def test_microphone_health_detects_read_failure() -> None:
    def _raiser() -> bytes:
        raise RuntimeError("mic read failed")

    health = MicrophoneHealth(audio_reader=_raiser)
    assert health.is_operational() is False
    assert health.last_error() == "MICROPHONE_READ_FAILURE"


def test_microphone_health_detects_repeated_no_input() -> None:
    health = MicrophoneHealth(audio_reader=lambda: b"", max_no_input_checks=2)
    assert health.is_operational() is True
    assert health.is_operational() is False
    assert health.last_error() == "MICROPHONE_NO_INPUT"

