from __future__ import annotations

from core.cognition.reasoning_engine import ReasoningEngine


class VeryLongLLMClient:
    def generate(self, prompt: str) -> str:
        _ = prompt
        sentence = (
            "Focus on one strategic objective, split it into milestones, and track completion signals"
        )
        return ". ".join([sentence] * 40) + "."


def test_reasoning_output_is_bounded_for_long_planning_request() -> None:
    engine = ReasoningEngine(llm_client=VeryLongLLMClient())
    output = engine.generate_strategy(
        {"goal": "build weekly planning strategy with detailed contingencies"}
    )

    assert output.safe_to_present is True
    assert len(output.summary) <= engine.MAX_REASONING_LENGTH
    assert len(" ".join(output.strategy_steps)) <= engine.MAX_REASONING_LENGTH
    assert len(output.strategy_steps) <= 5

    # Bound should prefer logical endings rather than abrupt token slicing.
    assert output.summary[-1].isalnum() or output.summary.endswith((".", "!", "?"))


def test_reasoning_bound_preserves_advisory_no_mutation_commands() -> None:
    engine = ReasoningEngine(llm_client=VeryLongLLMClient())
    output = engine.generate_strategy({"goal": "weekly planning"})

    rendered = f"{output.summary} {' '.join(output.strategy_steps)}".lower()
    forbidden = ("create_task(", "update_task(", "archive(", "delete(")
    assert not any(token in rendered for token in forbidden)

