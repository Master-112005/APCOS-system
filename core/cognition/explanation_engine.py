"""Deterministic template-based explanation rendering for command results."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Callable, Mapping

from core.cognition.command_router import CommandResult

TemplateFn = Callable[[dict[str, Any]], str]


class ExplanationEngine:
    """
    Convert structured command outcomes into deterministic user-facing text.

    This module is presentation-only and does not mutate state or call LLMs.
    """

    def __init__(self) -> None:
        self._action_templates: dict[tuple[str, str], TemplateFn] = {
            ("executed", "CREATE_TASK"): lambda _: "Your task has been scheduled successfully.",
            ("executed", "COMPLETE_TASK"): lambda _: "Your task has been marked as completed.",
            ("executed", "CANCEL_TASK"): lambda _: "Your task has been archived.",
            ("challenge_required", "COMPLETE_TASK"): lambda _: (
                "Before proceeding, please confirm this action aligns with your goal."
            ),
            ("challenge_required", "CANCEL_TASK"): lambda _: (
                "Before archiving, please confirm this action aligns with your goal."
            ),
        }
        self._error_templates: dict[str, TemplateFn] = {
            "LOW_CONFIDENCE": lambda _: (
                "I could not execute that because command confidence was too low."
            ),
            "INVALID_ENTITY": lambda _: "I could not execute that because details were invalid.",
            "INVALID_INTENT_SHAPE": lambda _: (
                "I could not execute that because the command format was invalid."
            ),
            "INVALID_TRANSITION": lambda _: (
                "I could not execute that because the lifecycle transition is not allowed."
            ),
            "UNSUPPORTED_INTENT": lambda _: "I could not execute that because the intent is unsupported.",
            "ACCESS_DENIED": lambda _: "Access denied for your current identity tier.",
            "INTERNAL_ERROR": lambda _: "I could not execute that due to an internal system error.",
        }

    def generate_response(self, command_result: CommandResult | Mapping[str, Any]) -> str:
        """Generate deterministic explanation text for a command result."""
        result = self._normalize_result(command_result)

        if result.get("error_code"):
            template = self._error_templates.get(str(result["error_code"]))
            if template:
                return template(result)

        key = (str(result.get("status", "")), str(result.get("action", "")))
        template = self._action_templates.get(key)
        if template:
            return template(result)

        fallback = self._error_templates.get("INTERNAL_ERROR")
        return fallback(result) if fallback else "I could not execute that due to an internal system error."

    @staticmethod
    def _normalize_result(command_result: CommandResult | Mapping[str, Any]) -> dict[str, Any]:
        if isinstance(command_result, Mapping):
            return dict(command_result)
        if is_dataclass(command_result):
            return asdict(command_result)
        raise TypeError("command_result must be CommandResult or mapping")
