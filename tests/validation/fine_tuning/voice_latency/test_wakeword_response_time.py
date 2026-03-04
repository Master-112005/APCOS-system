from __future__ import annotations

import time

from core.identity.identity_context import IdentityContext
from voice.asr_engine import ASREngine
from voice.tts_engine import TTSEngine
from voice.voice_session import VoiceSession
from voice.wake_word import WakeWordDetector


class ControllerStub:
    def __init__(self) -> None:
        self.identity: IdentityContext | None = None
        self.calls = 0

    def set_identity(self, identity: IdentityContext) -> None:
        self.identity = identity

    def handle_input(self, user_text: str) -> str:
        self.calls += 1
        return f"Acknowledged: {user_text}"


def test_wakeword_to_first_response_under_300ms_simulated() -> None:
    detector = WakeWordDetector(event_source=lambda: "hey apcos")
    controller = ControllerStub()
    asr = ASREngine()
    tts = TTSEngine()
    session = VoiceSession(
        wake_word_detector=detector,
        interaction_controller=controller,
        audio_capture=lambda: b"tier:owner;text:status check",
        asr_transcriber=asr.transcribe,
    )

    start = time.perf_counter()
    response = session.run_once()
    first_response_latency_ms = (time.perf_counter() - start) * 1000.0

    audio = tts.synthesize(response or "")
    tts_profile = tts.profile_snapshot()

    assert response is not None
    assert response == "Acknowledged: status check"
    assert controller.calls == 1
    assert controller.identity is not None
    assert controller.identity.tier == "OWNER"
    assert first_response_latency_ms < 300.0
    assert audio == b"Acknowledged: status check"
    assert tts_profile["sequence"] == 1

