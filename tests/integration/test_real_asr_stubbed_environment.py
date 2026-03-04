from __future__ import annotations

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


def _build_controller() -> tuple[InteractionController, TaskStore, CommandRouter]:
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
    return controller, store, router


def _push_wake_and_command(stream: AudioStream, command: bytes) -> None:
    stream.push_chunk(b"hey apcos")
    stream.push_chunk(command)


def test_real_voice_session_loads_model_once_and_routes_via_controller() -> None:
    controller, store, router = _build_controller()
    stream = AudioStream()
    wake = WakeWordEngine(audio_stream=stream, poll_interval=0.001)
    manager = ModelManager()
    asr = ASREngine(model_manager=manager, timeout_seconds=0.2)
    worker = TranscriptionWorker(asr_engine=asr, poll_interval=0.001)
    session = RealVoiceSession(
        wake_word_engine=wake,
        audio_stream=stream,
        transcription_worker=worker,
        interaction_controller=controller,
        transcription_timeout=0.2,
    )

    try:
        session.start()
        _push_wake_and_command(stream, b"tier:owner;text:Schedule review tomorrow at 9")
        time.sleep(0.02)
        result1 = session.run_once()
        assert result1 is not None and "scheduled successfully" in result1.lower()
        assert len(store.list_tasks(include_archived=True)) == 1
        assert manager.load_count == 1
        assert len(router.get_audit_events()) == 1

        _push_wake_and_command(stream, b"tier:owner;text:Schedule sync tomorrow at 10")
        time.sleep(0.02)
        result2 = session.run_once()
        assert result2 is not None and "scheduled successfully" in result2.lower()
        assert len(store.list_tasks(include_archived=True)) == 2
        assert manager.load_count == 1
        assert len(router.get_audit_events()) == 2
    finally:
        session.stop()


def test_real_voice_identity_enforcement_and_strategy_mode() -> None:
    controller, store, router = _build_controller()
    stream = AudioStream()
    wake = WakeWordEngine(audio_stream=stream, poll_interval=0.001)
    manager = ModelManager()
    asr = ASREngine(model_manager=manager, timeout_seconds=0.2)
    worker = TranscriptionWorker(asr_engine=asr, poll_interval=0.001)
    session = RealVoiceSession(
        wake_word_engine=wake,
        audio_stream=stream,
        transcription_worker=worker,
        interaction_controller=controller,
        transcription_timeout=0.2,
    )

    try:
        session.start()

        _push_wake_and_command(stream, b"tier:guest;text:Schedule payroll tomorrow at 9")
        time.sleep(0.02)
        denied = session.run_once()
        assert denied is not None and "access denied" in denied.lower()
        assert len(store.list_tasks(include_archived=True)) == 0
        assert len(router.get_audit_events()) == 0

        _push_wake_and_command(stream, b"tier:guest;text:/strategy help me plan goals")
        time.sleep(0.02)
        strategy = session.run_once()
        assert strategy is not None and "strategy:" in strategy.lower()
        assert len(store.list_tasks(include_archived=True)) == 0
        assert len(router.get_audit_events()) == 0
    finally:
        session.stop()
