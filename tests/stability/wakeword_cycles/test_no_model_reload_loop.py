from __future__ import annotations

from tests.validation.fixtures.wakeword_stability import (
    build_wakeword_stability_harness,
)


def test_no_model_reload_loop_across_1000_cycles() -> None:
    harness = build_wakeword_stability_harness(transcript="model reuse check")
    harness.run_cycles(1000)

    asr_profile = harness.asr.profile_snapshot()
    tts_profile = harness.tts.profile_snapshot()

    assert asr_profile["sequence"] == 1000
    assert asr_profile["model_load_count"] == 1
    assert asr_profile["pipeline_build_count"] == 1

    assert tts_profile["sequence"] == 1000
    assert tts_profile["pipeline_load_count"] == 1
