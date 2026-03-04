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
from core.memory.lifecycle_manager import LifecycleManager, TaskState
from core.memory.task_store import TaskStore
from interface.cli_shell import run_shell
from interface.interaction_controller import InteractionController


class ProactiveStub:
    def __init__(self) -> None:
        self.recalibrate_calls = 0

    def evaluate(self, context: dict[str, object]) -> list[dict[str, object]]:
        _ = context
        return [{"message": "You are drifting from your weekly plan."}]

    def recalibrate_threshold(self) -> float:
        self.recalibrate_calls += 1
        return 0.7


class ReasoningSpy:
    def __init__(self) -> None:
        self.calls = 0

    def generate_strategy(self, context: dict[str, object]) -> object:
        _ = context
        self.calls += 1
        return type(
            "Output",
            (),
            {
                "summary": "Plan one priority at a time.",
                "strategy_steps": ("Plan one priority at a time.",),
                "safe_to_present": True,
            },
        )()


def _build_controller(
    *,
    proactive_controller: object | None = None,
    reasoning_engine: object | None = None,
) -> tuple[InteractionController, TaskStore, CommandRouter]:
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
        proactive_controller=proactive_controller or ProactiveController(),
        explanation_engine=ExplanationEngine(),
        reasoning_engine=reasoning_engine or ReasoningEngine(),
        identity_resolver=IdentityResolver(),
        access_control=AccessControl(),
    )
    return controller, store, router


def test_schedule_task_via_controller() -> None:
    controller, store, _ = _build_controller()

    result = controller.handle_input("Schedule focus block tomorrow at 10")
    assert "scheduled successfully" in result.lower()
    tasks = store.list_tasks(include_archived=True)
    assert len(tasks) == 1
    assert tasks[0].title.lower() == "focus block"


def test_complete_task_via_controller() -> None:
    controller, store, _ = _build_controller()
    task = store.create_task(title="Workout")
    store.activate_task(task.task_id)

    result = controller.handle_input("Mark workout completed")
    assert "marked as completed" in result.lower()
    updated = store.get_task(task.task_id)
    assert updated is not None
    assert updated.state == TaskState.COMPLETED


def test_cancel_task_via_controller() -> None:
    controller, store, _ = _build_controller()
    task = store.create_task(title="Budget review")

    result = controller.handle_input("Cancel task budget review")
    assert "archived" in result.lower()
    updated = store.get_task(task.task_id)
    assert updated is not None
    assert updated.state == TaskState.ARCHIVED


def test_strategy_mode_does_not_mutate_state() -> None:
    controller, store, router = _build_controller()
    store.create_task(title="Existing task")

    before_tasks = len(store.list_tasks(include_archived=True))
    before_audits = len(router.get_audit_events())

    result = controller.handle_input("/strategy help me organize goals")
    assert "strategy:" in result.lower()

    after_tasks = len(store.list_tasks(include_archived=True))
    after_audits = len(router.get_audit_events())
    assert before_tasks == after_tasks
    assert before_audits == after_audits


def test_proactive_suggestion_displayed_after_command() -> None:
    proactive = ProactiveStub()
    controller, _, _ = _build_controller(proactive_controller=proactive)

    result = controller.handle_input("Schedule reading tomorrow at 9")
    assert "scheduled successfully" in result.lower()
    assert "proactive:" in result.lower()
    assert "drifting from your weekly plan" in result.lower()
    assert proactive.recalibrate_calls == 1


def test_reasoning_engine_not_called_during_crud_flow() -> None:
    reasoning = ReasoningSpy()
    controller, _, _ = _build_controller(reasoning_engine=reasoning)

    result = controller.handle_input("Schedule planning tomorrow at 8")
    assert "scheduled successfully" in result.lower()
    assert reasoning.calls == 0


def test_cli_shell_loop_help_and_exit(monkeypatch) -> None:
    controller, _, _ = _build_controller()
    inputs: Iterator[str] = iter(["help", "exit"])
    outputs: list[str] = []

    def fake_input(prompt: str) -> str:
        _ = prompt
        return next(inputs)

    def fake_output(message: str) -> None:
        outputs.append(message)

    run_shell(controller, input_func=fake_input, output_func=fake_output)

    joined = "\n".join(outputs).lower()
    assert "apcos cli ready" in joined
    assert "commands:" in joined
    assert "exiting apcos cli" in joined
