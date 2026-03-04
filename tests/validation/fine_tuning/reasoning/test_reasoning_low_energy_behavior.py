from __future__ import annotations

from core.cognition.reasoning_engine import ReasoningEngine


class MultiStepLLMClient:
    def generate(self, prompt: str) -> str:
        _ = prompt
        return (
            "Start with your highest-impact objective for the week. "
            "Break the objective into three clear milestones. "
            "Assign fixed focus windows and a daily review checkpoint."
        )


def test_low_energy_mode_returns_compressed_deterministic_structure() -> None:
    engine = ReasoningEngine(llm_client=MultiStepLLMClient())

    normal = engine.generate_strategy({"goal": "plan next week"})
    low_energy = engine.generate_strategy({"goal": "plan next week", "low_energy": True})

    assert normal.safe_to_present is True
    assert low_energy.safe_to_present is True
    assert low_energy.summary.startswith(engine.LOW_ENERGY_SUMMARY_PREFIX)
    assert len(low_energy.strategy_steps) <= 1
    assert len(low_energy.strategy_steps) < len(normal.strategy_steps)
    assert len(" ".join(low_energy.strategy_steps)) <= len(" ".join(normal.strategy_steps))


def test_low_energy_output_stays_advisory_only() -> None:
    engine = ReasoningEngine(llm_client=MultiStepLLMClient())
    output = engine.generate_strategy({"goal": "help me plan", "low_energy": True})

    rendered = f"{output.summary} {' '.join(output.strategy_steps)}".lower()
    forbidden = ("create_task(", "update_task(", "archive(", "delete(")
    assert not any(token in rendered for token in forbidden)
