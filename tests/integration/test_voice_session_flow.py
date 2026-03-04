from __future__ import annotations

from collections.abc import Iterator

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
from voice.voice_session import VoiceSession
from voice.wake_word import WakeWordDetector


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


def _event_source(events: list[str | None]):
    iterator: Iterator[str | None] = iter(events)

    def _read() -> str | None:
        try:
            return next(iterator)
        except StopIteration:
            return None

    return _read


def test_voice_session_wakeword_to_router_flow() -> None:
    controller, store, _ = _build_controller()
    detector = WakeWordDetector(event_source=_event_source(["hey apcos"]))
    session = VoiceSession(
        wake_word_detector=detector,
        interaction_controller=controller,
        audio_capture=lambda: b"tier:owner;text:Schedule reading tomorrow at 9",
    )

    response = session.run_once()
    assert response is not None
    assert "scheduled successfully" in response.lower()
    assert len(store.list_tasks(include_archived=True)) == 1


def test_voice_session_enforces_guest_access_control() -> None:
    controller, store, _ = _build_controller()
    detector = WakeWordDetector(event_source=_event_source(["hey apcos"]))
    session = VoiceSession(
        wake_word_detector=detector,
        interaction_controller=controller,
        audio_capture=lambda: b"tier:guest;text:Schedule sprint tomorrow at 10",
    )

    response = session.run_once()
    assert response is not None
    assert "access denied" in response.lower()
    assert len(store.list_tasks(include_archived=True)) == 0


def test_voice_session_strategy_mode_for_guest_has_no_mutation() -> None:
    controller, store, router = _build_controller()
    detector = WakeWordDetector(event_source=_event_source(["hey apcos"]))
    session = VoiceSession(
        wake_word_detector=detector,
        interaction_controller=controller,
        audio_capture=lambda: b"tier:guest;text:/strategy help me organize goals",
    )

    before_tasks = len(store.list_tasks(include_archived=True))
    before_audit = len(router.get_audit_events())
    response = session.run_once()
    after_tasks = len(store.list_tasks(include_archived=True))
    after_audit = len(router.get_audit_events())

    assert response is not None
    assert "strategy:" in response.lower()
    assert before_tasks == after_tasks
    assert before_audit == after_audit


def test_voice_session_resolves_identity_each_run() -> None:
    controller, store, _ = _build_controller()
    detector = WakeWordDetector(event_source=_event_source(["hey apcos", "hey apcos"]))
    captures = iter(
        [
            b"tier:guest;text:Schedule taxes tomorrow at 9",
            b"tier:owner;text:Schedule taxes tomorrow at 9",
        ]
    )
    session = VoiceSession(
        wake_word_detector=detector,
        interaction_controller=controller,
        audio_capture=lambda: next(captures),
    )

    first = session.run_once()
    second = session.run_once()

    assert first is not None and "access denied" in first.lower()
    assert second is not None and "scheduled successfully" in second.lower()
    assert len(store.list_tasks(include_archived=True)) == 1


def test_voice_session_returns_none_when_not_activated() -> None:
    controller, _, _ = _build_controller()
    detector = WakeWordDetector(event_source=_event_source(["background noise"]))
    session = VoiceSession(
        wake_word_detector=detector,
        interaction_controller=controller,
        audio_capture=lambda: b"tier:owner;text:Schedule planning tomorrow at 8",
    )

    assert session.run_once() is None
