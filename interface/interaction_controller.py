"""Thin orchestration layer for CLI interaction with APCOS cognitive core."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Callable, Mapping

from core.identity.access_control import AccessControl
from core.identity.identity_context import IdentityContext
from core.identity.identity_resolver import IdentityResolver


IntentParser = Callable[[str], dict[str, Any]]


@dataclass(frozen=True)
class StrategyRequest:
    """Normalized strategy request payload."""

    raw_query: str
    sanitized_query: str


class InteractionController:
    """
    Orchestrate user input through parser/router/explanation/proactive/reasoning.

    This layer does not mutate memory directly and does not contain lifecycle or
    parsing business rules.
    """

    def __init__(
        self,
        *,
        parser: IntentParser,
        router: Any,
        proactive_controller: Any,
        explanation_engine: Any,
        reasoning_engine: Any,
        identity_resolver: IdentityResolver,
        access_control: AccessControl,
    ) -> None:
        self._parser = parser
        self._router = router
        self._proactive_controller = proactive_controller
        self._explanation_engine = explanation_engine
        self._reasoning_engine = reasoning_engine
        self._identity_resolver = identity_resolver
        self._access_control = access_control
        self._identity = self._identity_resolver.default_identity()

    @property
    def current_identity(self) -> IdentityContext:
        """Return active session identity."""
        return self._identity

    def set_identity(self, identity: IdentityContext) -> None:
        """Set current session identity explicitly (used by voice session)."""
        self._identity = identity

    def handle_input(self, user_text: str) -> str:
        """Process one user input and return formatted CLI output."""
        text = (user_text or "").strip()
        if not text:
            return "Please enter a command."

        resolved_identity = self._identity_resolver.resolve_identity(text)
        if resolved_identity is not None:
            self._identity = resolved_identity
            return f"Logged in as {self._identity.tier}."

        if self._is_strategy_mode(text):
            if not self._access_control.is_allowed("strategy", self._identity):
                return self._access_denied_response("strategy")
            return self._handle_strategy_input(text)

        try:
            intent = self._parser(text)
            intent_type = str(intent.get("intent_type", ""))
            if not self._access_control.is_allowed(intent_type, self._identity):
                return self._access_denied_response(intent_type)
            command_result = self._router.route(intent)
            response = self._explanation_engine.generate_response(command_result)
        except Exception:
            return self._safe_internal_error()

        proactive_suffix = self._process_post_action(command_result)
        if proactive_suffix:
            return f"{response}\n{proactive_suffix}"
        return response

    def _handle_strategy_input(self, raw_text: str) -> str:
        request = self._parse_strategy_request(raw_text)
        if not request.sanitized_query:
            return "Provide a strategy request after /strategy."

        before_audit = self._router_audit_count()
        try:
            strategy_output = self._reasoning_engine.generate_strategy(
                {"goal": request.sanitized_query, "notes": request.sanitized_query}
            )
        except Exception:
            return self._safe_internal_error()

        after_audit = self._router_audit_count()
        if before_audit is not None and after_audit is not None and after_audit != before_audit:
            return self._safe_internal_error()

        safe_to_present = bool(getattr(strategy_output, "safe_to_present", False))
        if not safe_to_present:
            return self._safe_internal_error()

        summary = str(getattr(strategy_output, "summary", "")).strip()
        steps = tuple(getattr(strategy_output, "strategy_steps", ()))
        if not summary and not steps:
            return "No strategy available."

        lines = [f"Strategy: {summary}" if summary else "Strategy:"]
        for index, step in enumerate(steps[:5], start=1):
            cleaned = str(step).strip()
            if cleaned:
                lines.append(f"{index}. {cleaned}")
        return "\n".join(lines)

    def _process_post_action(self, command_result: Any) -> str:
        status = str(getattr(command_result, "status", ""))
        if status != "executed":
            return ""

        proactive_context = self._build_proactive_context(command_result)
        suggestions = self._scan_proactive(proactive_context)
        self._trigger_recalibration()
        if not suggestions:
            return ""

        rendered = []
        for suggestion in suggestions:
            if isinstance(suggestion, Mapping):
                message = str(suggestion.get("message", "")).strip()
            else:
                message = str(suggestion).strip()
            if message:
                rendered.append(f"Proactive: {message}")
        return "\n".join(rendered)

    @staticmethod
    def _is_strategy_mode(text: str) -> bool:
        lowered = text.lower()
        return lowered.startswith("/strategy") or lowered.startswith("strategy:")

    def _parse_strategy_request(self, text: str) -> StrategyRequest:
        cleaned = text.strip()
        if cleaned.lower().startswith("/strategy"):
            raw_query = cleaned[len("/strategy") :].strip()
        else:
            _, _, remainder = cleaned.partition(":")
            raw_query = remainder.strip()
        sanitized = self._sanitize_for_reasoning(raw_query)
        return StrategyRequest(raw_query=raw_query, sanitized_query=sanitized)

    @staticmethod
    def _sanitize_for_reasoning(text: str) -> str:
        # Keep strategy inputs bounded and remove control characters.
        normalized = re.sub(r"[\x00-\x1f\x7f]+", " ", text).strip()
        return normalized[:500]

    @staticmethod
    def _build_proactive_context(command_result: Any) -> dict[str, Any]:
        action = str(getattr(command_result, "action", ""))
        metadata = dict(getattr(command_result, "metadata", {}) or {})
        return {
            "last_action": action,
            "task_id": metadata.get("task_id"),
            "overdue_tasks": 0,
            "scheduled_tasks_today": 0,
            "goal_alignment_score": 1.0,
        }

    def _scan_proactive(self, context: Mapping[str, Any]) -> list[Any]:
        if hasattr(self._proactive_controller, "scan"):
            result = self._proactive_controller.scan(dict(context))
            return list(result or [])
        if hasattr(self._proactive_controller, "evaluate"):
            result = self._proactive_controller.evaluate(dict(context))
            return list(result or [])
        return []

    def _trigger_recalibration(self) -> None:
        if hasattr(self._proactive_controller, "recalibrate_threshold"):
            try:
                self._proactive_controller.recalibrate_threshold()
            except Exception:
                return

    def _router_audit_count(self) -> int | None:
        if not hasattr(self._router, "get_audit_events"):
            return None
        try:
            events = self._router.get_audit_events()
        except Exception:
            return None
        return len(events)

    def _safe_internal_error(self) -> str:
        return self._explanation_engine.generate_response(
            {
                "status": "rejected",
                "action": "UNKNOWN",
                "audit_id": "interaction-error",
                "message_key": "COMMAND_REJECTED",
                "metadata": {},
                "error_code": "INTERNAL_ERROR",
            }
        )

    def _access_denied_response(self, intent_type: str) -> str:
        return self._explanation_engine.generate_response(
            {
                "status": "rejected",
                "action": "UNKNOWN",
                "audit_id": "access-denied",
                "message_key": "COMMAND_REJECTED",
                "metadata": {
                    "intent_type": intent_type,
                    "identity_tier": self._identity.tier,
                },
                "error_code": "ACCESS_DENIED",
            }
        )
