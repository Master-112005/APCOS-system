from __future__ import annotations

from voice.audio_interface import capture_audio


def test_capture_audio_returns_bytes_stub() -> None:
    frame = capture_audio()
    assert isinstance(frame, bytes)
    assert frame == b"text:"
