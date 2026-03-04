from __future__ import annotations

from voice.asr_engine import ASREngine
from voice.tts_engine import TTSEngine
from voice.voice_session import VoiceSession
from voice.wake_word import WakeWordDetector


class _ControllerStub:
    def __init__(self) -> None:
        self.identity = None

    def set_identity(self, identity) -> None:  # type: ignore[no-untyped-def]
        self.identity = identity

    def handle_input(self, user_text: str) -> str:
        return f"ack:{user_text}"


def _make_session(*, controller: _ControllerStub, asr_engine: ASREngine, transcript: str) -> VoiceSession:
    detector = WakeWordDetector(event_source=lambda: "hey apcos")
    audio = f"tier:owner;text:{transcript}".encode("utf-8")
    return VoiceSession(
        wake_word_detector=detector,
        interaction_controller=controller,
        audio_capture=lambda: audio,
        asr_transcriber=asr_engine.transcribe,
    )


def test_voice_restart_reuses_asr_and_tts_pipeline() -> None:
    asr_engine = ASREngine()
    tts_engine = TTSEngine()

    controller_a = _ControllerStub()
    session_a = _make_session(controller=controller_a, asr_engine=asr_engine, transcript="first pass")
    response_a = str(session_a.run_once() or "")
    audio_a = tts_engine.synthesize(response_a)

    # Simulated controller restart: new controller + new VoiceSession on same model instances.
    controller_b = _ControllerStub()
    session_b = _make_session(controller=controller_b, asr_engine=asr_engine, transcript="second pass")
    response_b = str(session_b.run_once() or "")
    audio_b = tts_engine.synthesize(response_b)

    assert response_a == "ack:first pass"
    assert response_b == "ack:second pass"
    assert audio_a.startswith(b"ack:")
    assert audio_b.startswith(b"ack:")

    asr_profile = asr_engine.profile_snapshot()
    tts_profile = tts_engine.profile_snapshot()

    assert asr_profile["model_load_count"] == 1
    assert asr_profile["pipeline_build_count"] == 1
    assert asr_profile["sequence"] == 2

    assert tts_profile["pipeline_load_count"] == 1
    assert tts_profile["sequence"] == 2
