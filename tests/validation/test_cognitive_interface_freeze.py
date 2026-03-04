from __future__ import annotations

from dataclasses import fields
import inspect
import re
from typing import Any

from core.cognition.command_router import CommandRouter
from core.cognition.reasoning_engine import ReasoningEngine, StructuredReasoningOutput


MUTATION_PATTERN = re.compile(r"\b(create_task\s*\(|archive\s*\(|update_task\s*\(|delete\s*\()", re.IGNORECASE)


def _annotation_name(value: object) -> str:
    if value is inspect._empty:
        return ""
    if isinstance(value, str):
        return value
    return getattr(value, "__name__", str(value))


def test_router_signature_stability() -> None:
    signature = inspect.signature(CommandRouter.route)
    parameters = list(signature.parameters.values())

    assert [parameter.name for parameter in parameters] == ["self", "intent_object"]
    assert all(parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD for parameter in parameters)

    annotation = _annotation_name(signature.return_annotation)
    assert "CommandResult" in annotation


def test_reasoning_output_schema_stability() -> None:
    field_names = tuple(field.name for field in fields(StructuredReasoningOutput))
    assert field_names == ("summary", "strategy_steps", "safe_to_present", "blocked_reason")

    field_types = tuple(str(field.type) for field in fields(StructuredReasoningOutput))
    assert field_types[0] == "str"
    assert "tuple[str, ...]" in field_types[1]
    assert field_types[2] == "bool"


def test_reasoning_advisory_only_bounded_output() -> None:
    engine = ReasoningEngine()
    output = engine.generate_strategy({"goal": "Plan and prioritize this week", "notes": "Keep it concise"})

    assert isinstance(output, StructuredReasoningOutput)
    assert output.safe_to_present is True
    assert len(output.summary) <= engine.MAX_REASONING_LENGTH
    assert not MUTATION_PATTERN.search(output.summary)
    assert all(not MUTATION_PATTERN.search(step) for step in output.strategy_steps)


def test_reasoning_low_energy_output_contract() -> None:
    engine = ReasoningEngine()
    output = engine.generate_strategy(
        {
            "goal": "Plan quarterly deliverables",
            "notes": "Conserve compute",
            "low_energy": True,
        }
    )
    assert output.safe_to_present is True
    assert output.summary.startswith(engine.LOW_ENERGY_SUMMARY_PREFIX)
    assert len(output.summary) <= engine.MAX_REASONING_LENGTH
    assert len(output.strategy_steps) <= 1


def test_reasoning_ambiguous_request_stays_advisory() -> None:
    engine = ReasoningEngine()
    output = engine.generate_strategy({"goal": "maybe change my tasks"})
    assert output.safe_to_present is True
    assert output.summary == engine.ADVISORY_ONLY_MESSAGE
    assert "confirm" in output.summary.lower()

    payload: dict[str, Any] = {
        "summary": output.summary,
        "strategy_steps": output.strategy_steps,
        "safe_to_present": output.safe_to_present,
        "blocked_reason": output.blocked_reason,
    }
    assert set(payload.keys()) == {"summary", "strategy_steps", "safe_to_present", "blocked_reason"}
