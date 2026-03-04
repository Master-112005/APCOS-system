from __future__ import annotations

from voice.tts_engine import TTSEngine


def test_tts_startup_latency_improves_after_warmup() -> None:
    engine = TTSEngine()

    first_audio = engine.synthesize("APCOS voice response ready.")
    first_profile = engine.profile_snapshot()

    second_audio = engine.synthesize("APCOS voice response ready.")
    second_profile = engine.profile_snapshot()

    assert first_audio == b"APCOS voice response ready."
    assert second_audio == b"APCOS voice response ready."

    assert first_profile["cold_start"] is True
    assert second_profile["cold_start"] is False
    assert second_profile["cache_reused"] is True
    assert second_profile["pipeline_load_count"] == 1
    assert second_profile["total_latency_ms"] < first_profile["total_latency_ms"]
    assert second_profile["playback_latency_ms"] >= 0.0

