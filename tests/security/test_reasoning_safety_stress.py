from __future__ import annotations

import pytest

from core.cognition.reasoning_engine import ReasoningEngine


class FixedOutputLLMClient:
    def __init__(self, output: str) -> None:
        self._output = output

    def generate(self, prompt: str) -> str:
        _ = prompt
        return self._output


@pytest.mark.parametrize(
    "unsafe_text",
    [
        "delete the task",
        "archive everything now",
        "archive all tasks before noon",
        "call lifecycle_manager.transition immediately",
        "directly modify database rows",
        "bypass router and force update",
        "reduce threshold to zero to increase interventions",
    ],
)
def test_reasoning_engine_rejects_adversarial_mutation_terms(unsafe_text: str) -> None:
    engine = ReasoningEngine(llm_client=FixedOutputLLMClient(unsafe_text))
    output = engine.generate_strategy({"goal": "Protect system integrity"})

    assert output.safe_to_present is False
    assert output.blocked_reason is not None
    assert output.blocked_reason.startswith("UNSAFE_TOKEN:")
    assert output.strategy_steps == ()

    rendered = f"{output.summary} {' '.join(output.strategy_steps)}".lower()
    forbidden_terms = [
        "delete",
        "archive",
        "lifecycle",
        "transition",
        "database",
        "router",
        "threshold",
    ]
    for term in forbidden_terms:
        assert term not in rendered
