from __future__ import annotations

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


def _build_controller() -> tuple[InteractionController, TaskStore]:
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
    return controller, store


def test_guest_cannot_schedule_but_owner_can() -> None:
    controller, store = _build_controller()
    assert len(store.list_tasks(include_archived=True)) == 0

    login_guest = controller.handle_input("login guest")
    assert "logged in as guest" in login_guest.lower()

    denied = controller.handle_input("Schedule planning tomorrow at 10")
    assert "access denied" in denied.lower()
    assert len(store.list_tasks(include_archived=True)) == 0

    login_owner = controller.handle_input("login owner")
    assert "logged in as owner" in login_owner.lower()

    allowed = controller.handle_input("Schedule planning tomorrow at 10")
    assert "scheduled successfully" in allowed.lower()
    assert len(store.list_tasks(include_archived=True)) == 1


def test_strategy_mode_allowed_for_guest_without_mutation() -> None:
    controller, store = _build_controller()

    controller.handle_input("login guest")
    before = len(store.list_tasks(include_archived=True))
    result = controller.handle_input("/strategy help me plan my week")
    after = len(store.list_tasks(include_archived=True))

    assert "strategy:" in result.lower()
    assert before == after
