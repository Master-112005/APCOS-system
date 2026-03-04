from __future__ import annotations

from core.cognition.challenge_logic import ChallengeLogic
from core.cognition.command_router import CommandRouter
from core.cognition.reasoning_engine import ReasoningEngine
from core.memory.lifecycle_manager import LifecycleManager
from core.memory.task_store import TaskStore


class FailingLLMClient:
    def generate(self, prompt: str) -> str:
        _ = prompt
        raise RuntimeError("offline")


class UnsafeLLMClient:
    def generate(self, prompt: str) -> str:
        _ = prompt
        return "Delete the task and force lifecycle transition immediately."


class SafeLLMClient:
    def generate(self, prompt: str) -> str:
        _ = prompt
        return (
            "Start with your top priority for 45 minutes. "
            "Then schedule a short review block."
        )


def test_reasoning_engine_handles_llm_failures() -> None:
    engine = ReasoningEngine(llm_client=FailingLLMClient())
    output = engine.generate_strategy({"goal": "Ship Stage 2"})

    assert output.safe_to_present is False
    assert output.blocked_reason == "LLM_FAILURE"
    assert output.strategy_steps == ()


def test_reasoning_engine_filters_unsafe_output() -> None:
    engine = ReasoningEngine(llm_client=UnsafeLLMClient())
    output = engine.generate_strategy({"goal": "Stay focused"})

    assert output.safe_to_present is False
    assert output.blocked_reason is not None
    assert output.blocked_reason.startswith("UNSAFE_TOKEN:")
    assert output.strategy_steps == ()


def test_reasoning_engine_returns_structured_safe_strategy() -> None:
    engine = ReasoningEngine(llm_client=SafeLLMClient())
    output = engine.generate_strategy({"goal": "Ship Stage 2", "notes": "Avoid multitasking"})

    assert output.safe_to_present is True
    assert len(output.strategy_steps) >= 2
    assert "top priority" in output.summary.lower()


def test_reasoning_engine_does_not_affect_router_or_memory_state() -> None:
    lifecycle = LifecycleManager()
    store = TaskStore(lifecycle_manager=lifecycle)
    router = CommandRouter(
        task_store=store,
        lifecycle_manager=lifecycle,
        challenge_logic=ChallengeLogic(),
        config_path="configs/default.yaml",
    )
    store.create_task(title="Read architecture notes")

    before_tasks = len(store.list_tasks(include_archived=True))
    before_audit = len(router.get_audit_events())

    engine = ReasoningEngine(llm_client=SafeLLMClient())
    _ = engine.generate_strategy({"goal": "Improve planning quality"})

    after_tasks = len(store.list_tasks(include_archived=True))
    after_audit = len(router.get_audit_events())

    assert before_tasks == after_tasks
    assert before_audit == after_audit
