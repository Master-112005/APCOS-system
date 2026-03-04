from __future__ import annotations

import threading
import time

from core.cognition.challenge_logic import ChallengeLogic
from core.cognition.command_router import CommandRouter
from core.cognition.explanation_engine import ExplanationEngine
from core.cognition.intent_parser import parse_intent
from core.cognition.proactive_controller import ProactiveController
from core.cognition.reasoning_engine import ReasoningEngine
from core.identity.access_control import AccessControl
from core.identity.identity_resolver import IdentityResolver
from core.memory.lifecycle_manager import LifecycleManager
from core.memory.task_store import TaskStore
from interface.interaction_controller import InteractionController
from voice.asr_engine_real import ASREngine
from voice.audio_stream import AudioStream
from voice.model_manager import ModelManager
from voice.transcription_worker import TranscriptionWorker
from voice.voice_session import RealVoiceSession
from voice.wake_word_engine import WakeWordEngine


def _build_controller() -> tuple[InteractionController, CommandRouter]:
    lifecycle = LifecycleManager()
    store = TaskStore(lifecycle_manager=lifecycle)
    router = CommandRouter(
        task_store=store,
        lifecycle_manager=lifecycle,
        challenge_logic=ChallengeLogic(),
        config_path="configs/default.yaml",
    )
    controller = InteractionController(
        parser=parse_intent,
        router=router,
        proactive_controller=ProactiveController(),
        explanation_engine=ExplanationEngine(),
        reasoning_engine=ReasoningEngine(),
        identity_resolver=IdentityResolver(),
        access_control=AccessControl(),
    )
    return controller, router


def test_wake_word_engine_rapid_start_stop_is_thread_safe() -> None:
    stream = AudioStream()
    stream.start()
    engine = WakeWordEngine(audio_stream=stream, poll_interval=0.001)

    for _ in range(20):
        engine.start()
        time.sleep(0.002)
        engine.stop()
        assert engine.is_running() is False

    stream.stop()


def test_transcription_worker_handles_burst_audio_without_crash() -> None:
    manager = ModelManager()
    asr = ASREngine(model_manager=manager, timeout_seconds=0.2)
    worker = TranscriptionWorker(asr_engine=asr, max_queue_size=128, poll_interval=0.001)
    worker.start()

    def producer(prefix: str) -> None:
        for idx in range(100):
            worker.submit_audio(f"tier:owner;text:{prefix}-{idx}".encode("utf-8"))

    threads = [threading.Thread(target=producer, args=(f"p{i}",), daemon=True) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    time.sleep(0.1)
    received = 0
    for _ in range(400):
        value = worker.get_transcription(timeout=0.001)
        if value:
            received += 1

    worker.stop()
    assert received > 0
    assert worker.is_running() is False


def test_model_load_once_under_concurrency() -> None:
    calls = {"loader_calls": 0}

    class DummyModel:
        backend_name = "dummy"

        def transcribe_bytes(self, audio_bytes: bytes) -> str:
            _ = audio_bytes
            return "ok"

    def loader():  # type: ignore[no-untyped-def]
        calls["loader_calls"] += 1
        time.sleep(0.005)
        return DummyModel()

    manager = ModelManager(model_loader=loader)

    def load_worker() -> None:
        for _ in range(20):
            manager.load_asr_model()

    threads = [threading.Thread(target=load_worker, daemon=True) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert manager.load_count == 1
    assert calls["loader_calls"] == 1


def test_no_router_calls_from_worker_thread() -> None:
    controller, router = _build_controller()
    stream = AudioStream()
    wake = WakeWordEngine(audio_stream=stream, poll_interval=0.001)
    manager = ModelManager()
    asr = ASREngine(model_manager=manager, timeout_seconds=0.2)
    worker = TranscriptionWorker(asr_engine=asr, poll_interval=0.001)

    call_threads: list[str] = []
    original_route = router.route

    def wrapped_route(intent):  # type: ignore[no-untyped-def]
        call_threads.append(threading.current_thread().name)
        return original_route(intent)

    router.route = wrapped_route  # type: ignore[assignment]
    session = RealVoiceSession(
        wake_word_engine=wake,
        audio_stream=stream,
        transcription_worker=worker,
        interaction_controller=controller,
        transcription_timeout=0.2,
    )

    try:
        session.start()
        for idx in range(5):
            stream.push_chunk(b"hey apcos")
            stream.push_chunk(f"tier:owner;text:Schedule burst {idx} tomorrow at 9".encode("utf-8"))
            time.sleep(0.01)
            response = session.run_once()
            assert response is not None
    finally:
        session.stop()
        router.route = original_route  # type: ignore[assignment]

    assert call_threads
    assert set(call_threads) == {threading.current_thread().name}
