from __future__ import annotations

from tests.validation.fixtures.energy_runtime_load import (
    MockTTS,
    build_energy_runtime_harness,
)


def test_voice_pipeline_continues_under_critical_with_heavy_path_blocked() -> None:
    harness = build_energy_runtime_harness()
    tts = MockTTS()
    baseline_audits = harness.router_audit_count()

    harness.sync_burst(count=8, source_prefix="sync-voice")
    harness.set_battery(5)

    heavy_session = harness.build_voice_session(transcript="/strategy help me organize priorities")
    heavy_response = heavy_session.run_once()
    heavy_audio = tts.speak(heavy_response or "")

    light_session = harness.build_voice_session(transcript="status check")
    light_response = light_session.run_once()
    light_audio = tts.speak(light_response or "")

    assert heavy_response is not None
    assert "energy gate:" in heavy_response.lower()
    assert "blocked_critical" in heavy_response.lower()

    assert light_response is not None
    assert "voice command acknowledged" in light_response.lower()

    assert heavy_audio
    assert light_audio
    assert harness.router_audit_count() == baseline_audits

    assert any(
        decision["mode"] == "CRITICAL"
        and decision["execution_type"] == "LLM"
        and decision["allowed"] is False
        for decision in harness.energy_state.decisions
    )
    assert any(
        decision["mode"] == "CRITICAL"
        and decision["execution_type"] == "VOICE"
        and decision["allowed"] is True
        for decision in harness.energy_state.decisions
    )

