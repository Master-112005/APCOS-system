from __future__ import annotations

from core.cognition.command_router import CommandResult
from core.cognition.explanation_engine import ExplanationEngine


def test_explanation_engine_returns_executed_template() -> None:
    engine = ExplanationEngine()
    result = CommandResult(
        status="executed",
        action="CREATE_TASK",
        audit_id="a1",
        message_key="COMMAND_EXECUTED",
        metadata={"task_id": 1},
    )

    text = engine.generate_response(result)
    assert text == "Your task has been scheduled successfully."


def test_explanation_engine_maps_error_codes() -> None:
    engine = ExplanationEngine()
    result = CommandResult(
        status="rejected",
        action="UNKNOWN",
        audit_id="a2",
        message_key="COMMAND_REJECTED",
        metadata={},
        error_code="LOW_CONFIDENCE",
    )

    text = engine.generate_response(result)
    assert "confidence was too low" in text


def test_explanation_engine_challenge_flow_is_advisory() -> None:
    engine = ExplanationEngine()
    result = CommandResult(
        status="challenge_required",
        action="CANCEL_TASK",
        audit_id="a3",
        message_key="CHALLENGE_REQUIRED",
        metadata={},
        challenge_payload={"challenge_id": "c1"},
    )

    text = engine.generate_response(result)
    assert "confirm" in text.lower()
    assert "aligns with your goal" in text.lower()


def test_explanation_engine_internal_error_fallback() -> None:
    engine = ExplanationEngine()
    result = {
        "status": "rejected",
        "action": "COMPLETE_TASK",
        "audit_id": "a4",
        "message_key": "COMMAND_REJECTED",
        "metadata": {},
        "error_code": "INTERNAL_ERROR",
    }

    text = engine.generate_response(result)
    assert "internal system error" in text.lower()


def test_explanation_engine_access_denied_mapping() -> None:
    engine = ExplanationEngine()
    result = CommandResult(
        status="rejected",
        action="UNKNOWN",
        audit_id="a5",
        message_key="COMMAND_REJECTED",
        metadata={},
        error_code="ACCESS_DENIED",
    )

    text = engine.generate_response(result)
    assert "access denied" in text.lower()
