from __future__ import annotations

from voice.asr_engine import transcribe


def test_asr_transcribe_extracts_text_marker_payload() -> None:
    audio = b"tier:owner;text:Schedule reading tomorrow at 9"
    assert transcribe(audio) == "Schedule reading tomorrow at 9"


def test_asr_transcribe_returns_empty_for_unmarked_payload() -> None:
    assert transcribe(b"raw_audio_bytes") == ""
