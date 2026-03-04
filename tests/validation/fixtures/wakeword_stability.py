"""Fixtures for continuous wakeword-cycle stability validation."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

from core.identity.identity_context import IdentityContext
from voice.asr_engine import ASREngine
from voice.tts_engine import TTSEngine
from voice.voice_session import VoiceSession
from voice.wake_word import WakeWordDetector


@dataclass(frozen=True)
class CycleMeasurement:
    """Per-cycle latency and output snapshot for stability assertions."""

    cycle_index: int
    wake_to_response_ms: float
    asr_total_latency_ms: float
    tts_total_latency_ms: float
    response: str


class ReasoningStubController:
    """Deterministic response stub used to emulate cognition output."""

    def __init__(self) -> None:
        self.identity: IdentityContext | None = None
        self.calls = 0

    def set_identity(self, identity: IdentityContext) -> None:
        self.identity = identity

    def handle_input(self, user_text: str) -> str:
        self.calls += 1
        return f"Advisory: {(user_text or '').strip()}"


class WakewordStabilityHarness:
    """Single-process wakeword -> ASR -> reasoning-stub -> TTS loop harness."""

    def __init__(self, *, transcript: str = "status check") -> None:
        self.asr = ASREngine()
        self.tts = TTSEngine()
        self.controller = ReasoningStubController()
        self._audio = f"tier:owner;text:{transcript}".encode("utf-8")
        self._session = VoiceSession(
            wake_word_detector=WakeWordDetector(event_source=lambda: "hey apcos"),
            interaction_controller=self.controller,
            audio_capture=lambda: self._audio,
            asr_transcriber=self.asr.transcribe,
        )

    def run_cycle(self, cycle_index: int) -> CycleMeasurement:
        start = time.perf_counter()
        response = self._session.run_once()
        wake_to_response_ms = (time.perf_counter() - start) * 1000.0
        if response is None:
            raise RuntimeError("wakeword cycle did not activate")
        self.tts.synthesize(response)
        asr_profile = self.asr.profile_snapshot()
        tts_profile = self.tts.profile_snapshot()
        return CycleMeasurement(
            cycle_index=cycle_index,
            wake_to_response_ms=wake_to_response_ms,
            asr_total_latency_ms=float(asr_profile["total_latency_ms"]),
            tts_total_latency_ms=float(tts_profile["total_latency_ms"]),
            response=response,
        )

    def run_cycles(self, total_cycles: int) -> list[CycleMeasurement]:
        if total_cycles <= 0:
            return []
        measurements: list[CycleMeasurement] = []
        for index in range(total_cycles):
            measurements.append(self.run_cycle(index))
        return measurements


def build_wakeword_stability_harness(*, transcript: str = "status check") -> WakewordStabilityHarness:
    """Factory for deterministic wakeword-cycle stability scenarios."""
    return WakewordStabilityHarness(transcript=transcript)
