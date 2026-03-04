"""Single-run voice session orchestration for APCOS voice layer."""

from __future__ import annotations

import time
from typing import Any, Callable

from core.behavior.resource_governor import ResourceGovernor
from core.identity.identity_context import IdentityContext
from voice.asr_engine_real import ASREngine
from voice.audio_stream import AudioStream
from voice.asr_engine import transcribe
from voice.audio_interface import capture_audio
from voice.transcription_worker import TranscriptionWorker
from voice.voice_identity_stub import resolve_voice_identity
from voice.wake_word import WakeWordDetector
from voice.wake_word_engine import WakeWordEngine

AudioCaptureFn = Callable[[], bytes]
TranscribeFn = Callable[[bytes], str]
VoiceIdentityFn = Callable[[bytes], IdentityContext]


class VoiceSession:
    """
    Orchestrate one voice interaction cycle.

    Flow:
    wake word -> audio capture -> identity resolve -> ASR -> interaction controller
    """

    def __init__(
        self,
        *,
        wake_word_detector: WakeWordDetector,
        interaction_controller: Any,
        audio_capture: AudioCaptureFn = capture_audio,
        asr_transcriber: TranscribeFn = transcribe,
        voice_identity_resolver: VoiceIdentityFn = resolve_voice_identity,
    ) -> None:
        self._wake_word_detector = wake_word_detector
        self._interaction_controller = interaction_controller
        self._audio_capture = audio_capture
        self._asr_transcriber = asr_transcriber
        self._voice_identity_resolver = voice_identity_resolver

    def run_once(self) -> str | None:
        """Run one wake-to-response cycle and return rendered response if available."""
        if not self._wake_word_detector.listen():
            return None

        try:
            audio = bytes(self._audio_capture())
        except Exception:
            return "I could not execute that due to an internal system error."

        if not audio:
            return "No speech detected."

        identity = self._voice_identity_resolver(audio)
        if hasattr(self._interaction_controller, "set_identity"):
            self._interaction_controller.set_identity(identity)

        transcript = self._asr_transcriber(audio).strip()
        if not transcript:
            return "No speech detected."

        try:
            return self._interaction_controller.handle_input(transcript)
        except Exception:
            return "I could not execute that due to an internal system error."


class RealVoiceSession:
    """
    Real voice pipeline session using wake thread + ASR worker thread.

    This session preserves mutation boundaries: only main thread calls
    interaction_controller.handle_input().
    """

    def __init__(
        self,
        *,
        wake_word_engine: WakeWordEngine,
        audio_stream: AudioStream,
        transcription_worker: TranscriptionWorker,
        interaction_controller: Any,
        voice_identity_resolver: Callable[..., IdentityContext] = resolve_voice_identity,
        transcription_timeout: float = 0.4,
        idle_unload_seconds: float = 300.0,
        resource_governor: ResourceGovernor | None = None,
        device_state_manager: Any | None = None,
    ) -> None:
        self._wake_word_engine = wake_word_engine
        self._audio_stream = audio_stream
        self._transcription_worker = transcription_worker
        self._interaction_controller = interaction_controller
        self._voice_identity_resolver = voice_identity_resolver
        self._transcription_timeout = max(0.05, float(transcription_timeout))
        self._idle_unload_seconds = max(1.0, float(idle_unload_seconds))
        self._resource_governor = resource_governor
        self._device_state_manager = device_state_manager
        self._started = False
        self._last_activity = time.monotonic()

    def start(self) -> None:
        """Start stream, wake engine, and transcription worker once."""
        if self._started:
            return
        self._audio_stream.start()
        worker_started = self._transcription_worker.start()
        if not worker_started:
            self._audio_stream.stop()
            return
        self._wake_word_engine.start()
        if self._resource_governor is not None:
            self._resource_governor.start()
        self._started = True

    def stop(self) -> None:
        """Stop all runtime components and release model resources."""
        if not self._started:
            return
        self._wake_word_engine.stop()
        self._transcription_worker.stop()
        self._audio_stream.stop()
        if self._resource_governor is not None:
            self._resource_governor.stop()
        self._transcription_worker.asr_engine.model_manager.unload_asr_model()
        self._started = False

    def run_once(self) -> str | None:
        """Run one real voice cycle if a wake event is available."""
        self.start()
        if not self._started:
            return "Voice runtime is busy."

        if self._evaluate_device_state() == "SLEEP":
            return None

        if not self._wake_word_engine.wait_for_wake(timeout=0.01):
            self._maybe_unload_if_idle()
            self._evaluate_governor()
            return None

        audio = self._audio_stream.read_chunk()
        if not audio:
            return "No speech detected."

        if not self._transcription_worker.submit_audio(audio):
            return "No speech detected."

        transcript = self._transcription_worker.get_transcription(timeout=self._transcription_timeout)
        if transcript is None or not transcript.strip():
            return "No speech detected."

        # Identity resolution occurs after transcription for Stage 7.
        identity = self._voice_identity_resolver(audio, transcript=transcript)
        if hasattr(self._interaction_controller, "set_identity"):
            self._interaction_controller.set_identity(identity)

        self._last_activity = time.monotonic()
        try:
            response = self._interaction_controller.handle_input(transcript)
            self._evaluate_governor()
            return response
        except Exception:
            return "I could not execute that due to an internal system error."

    def _maybe_unload_if_idle(self) -> None:
        idle_for = time.monotonic() - self._last_activity
        if idle_for < self._idle_unload_seconds:
            return
        self._transcription_worker.asr_engine.unload_if_idle(self._idle_unload_seconds)

    def _evaluate_governor(self) -> None:
        if self._resource_governor is None:
            return
        self._resource_governor.evaluate()

    def _evaluate_device_state(self) -> str | None:
        if self._device_state_manager is None:
            return None
        try:
            snapshot = self._device_state_manager.evaluate_state()
        except Exception:
            return None
        try:
            return str(snapshot.get("state"))
        except Exception:
            return None
