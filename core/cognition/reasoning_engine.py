"""Controlled advisory reasoning layer with post-validation safeguards."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Protocol


class LLMClient(Protocol):
    """Interface for pluggable local LLM providers."""

    def generate(self, prompt: str) -> str:
        """Return generated text for a prompt."""


@dataclass(frozen=True)
class StructuredReasoningOutput:
    """Typed response contract for advisory reasoning results."""

    summary: str
    strategy_steps: tuple[str, ...]
    safe_to_present: bool
    blocked_reason: str | None = None


class StubLLMClient:
    """Default local stub client used when no LLM provider is configured."""

    def generate(self, prompt: str) -> str:
        _ = prompt
        return (
            "Focus on your highest-priority goal first. "
            "Break work into small time-boxed actions. "
            "Review progress at the end of the day."
        )


class ReasoningEngine:
    """
    Advisory-only reasoning engine.

    Safety constraints:
    - no task or lifecycle mutation
    - no router calls
    - no threshold modification
    - unsafe LLM output is rejected by post-validation
    """

    _UNSAFE_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(r"\bdelete\b", re.IGNORECASE),
        re.compile(r"\bdrop\b", re.IGNORECASE),
        re.compile(r"\bcreate\s+task\b", re.IGNORECASE),
        re.compile(r"\bcomplete\s+task\b", re.IGNORECASE),
        re.compile(r"\bcancel\s+task\b", re.IGNORECASE),
        re.compile(r"\barchive\s+task\b", re.IGNORECASE),
        re.compile(r"\barchive\b.*\b(task|tasks|all|everything)\b", re.IGNORECASE),
        re.compile(r"\blifecycle\b", re.IGNORECASE),
        re.compile(r"\blifecycle_manager\b", re.IGNORECASE),
        re.compile(r"\btransition\b", re.IGNORECASE),
        re.compile(r"\btask_store\b", re.IGNORECASE),
        re.compile(r"\bcommand_router\b", re.IGNORECASE),
        re.compile(r"\bbypass\s+router\b", re.IGNORECASE),
        re.compile(r"\bmodify\b.*\bdatabase\b", re.IGNORECASE),
        re.compile(r"\bdatabase\b", re.IGNORECASE),
        re.compile(r"\breduce\s+threshold\b", re.IGNORECASE),
        re.compile(r"\bthreshold\b.*\bzero\b", re.IGNORECASE),
    )
    _MUTATION_COMMAND_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(r"\bcreate_task\s*\(", re.IGNORECASE),
        re.compile(r"\barchive\s*\(", re.IGNORECASE),
        re.compile(r"\bupdate_task\s*\(", re.IGNORECASE),
        re.compile(r"\bdelete\s*\(", re.IGNORECASE),
    )
    _AMBIGUOUS_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(r"\bmaybe\b.*\b(change|update|fix)\b.*\btask", re.IGNORECASE),
        re.compile(r"\b(change|update|fix)\b.*\btask", re.IGNORECASE),
        re.compile(r"\bnot sure\b", re.IGNORECASE),
        re.compile(r"\bsomehow\b", re.IGNORECASE),
    )
    MAX_REASONING_LENGTH = 420
    ADVISORY_ONLY_MESSAGE = "This is an explanation only. Actions require user confirmation."
    LOW_ENERGY_SUMMARY_PREFIX = "Low-energy strategy:"

    def __init__(self, *, llm_client: LLMClient | None = None) -> None:
        self._llm_client = llm_client or StubLLMClient()

    def generate_strategy(self, context: Mapping[str, Any]) -> StructuredReasoningOutput:
        """
        Generate structured advisory strategy from safe context.

        The result is strictly advisory and must never be interpreted as command
        execution input.
        """
        safe_context = self._sanitize_context(context)
        if self._is_ambiguous_request(safe_context):
            return StructuredReasoningOutput(
                summary=self.ADVISORY_ONLY_MESSAGE,
                strategy_steps=(
                    "Clarify your exact objective before requesting strategy output.",
                ),
                safe_to_present=True,
            )

        prompt = self._build_prompt(safe_context)

        try:
            raw = self._llm_client.generate(prompt)
        except Exception:
            return StructuredReasoningOutput(
                summary="Strategy generation is temporarily unavailable.",
                strategy_steps=(),
                safe_to_present=False,
                blocked_reason="LLM_FAILURE",
            )

        if self._has_mutation_command(raw):
            bounded_advisory = self._bound_text(self.ADVISORY_ONLY_MESSAGE)
            return StructuredReasoningOutput(
                summary=bounded_advisory,
                strategy_steps=(),
                safe_to_present=True,
            )

        unsafe_reason = self._find_unsafe_reason(raw)
        if unsafe_reason is not None:
            return StructuredReasoningOutput(
                summary=self._bound_text(self.ADVISORY_ONLY_MESSAGE),
                strategy_steps=(),
                safe_to_present=False,
                blocked_reason=unsafe_reason,
            )

        bounded_text = self._bound_text(raw)
        steps = self._extract_steps(bounded_text)
        if bool(safe_context.get("low_energy", False)):
            return self._compress_low_energy_output(steps)

        summary = steps[0] if steps else "No strategy available."
        return StructuredReasoningOutput(
            summary=summary,
            strategy_steps=tuple(steps),
            safe_to_present=True,
        )

    @staticmethod
    def _sanitize_context(context: Mapping[str, Any]) -> dict[str, Any]:
        allowed_keys = {"goal", "constraints", "horizon_days", "priorities", "notes", "low_energy"}
        sanitized: dict[str, Any] = {}
        for key in allowed_keys:
            if key in context:
                sanitized[key] = context[key]
        return sanitized

    @staticmethod
    def _build_prompt(context: Mapping[str, Any]) -> str:
        return (
            "Generate concise advisory strategy for the provided context only.\n"
            f"Context: {dict(context)}\n"
            "Do not output commands, lifecycle operations, or deletion instructions."
        )

    def _find_unsafe_reason(self, generated_text: str) -> str | None:
        for pattern in self._UNSAFE_PATTERNS:
            if pattern.search(generated_text):
                return f"UNSAFE_TOKEN:{pattern.pattern}"
        return None

    def _has_mutation_command(self, generated_text: str) -> bool:
        for pattern in self._MUTATION_COMMAND_PATTERNS:
            if pattern.search(generated_text):
                return True
        return False

    def _is_ambiguous_request(self, context: Mapping[str, Any]) -> bool:
        request_text = " ".join(
            str(context.get(key, ""))
            for key in ("goal", "notes", "constraints")
        ).strip()
        if not request_text:
            return False
        for pattern in self._AMBIGUOUS_PATTERNS:
            if pattern.search(request_text):
                return True
        return False

    def _compress_low_energy_output(self, steps: list[str]) -> StructuredReasoningOutput:
        if not steps:
            summary = f"{self.LOW_ENERGY_SUMMARY_PREFIX} Keep one priority and defer optional work."
            return StructuredReasoningOutput(
                summary=self._bound_text(summary),
                strategy_steps=(),
                safe_to_present=True,
            )

        compact_step = self._bound_text(steps[0], max_length=140)
        summary = f"{self.LOW_ENERGY_SUMMARY_PREFIX} {compact_step}"
        return StructuredReasoningOutput(
            summary=self._bound_text(summary),
            strategy_steps=(compact_step,),
            safe_to_present=True,
        )

    def _bound_text(self, text: str, *, max_length: int | None = None) -> str:
        limit = int(max_length or self.MAX_REASONING_LENGTH)
        compact = " ".join(str(text).split())
        if len(compact) <= limit:
            return compact

        cut = compact[:limit]
        for delimiter in (". ", "! ", "? "):
            index = cut.rfind(delimiter)
            if index > int(limit * 0.5):
                return cut[: index + 1].strip()

        space_index = cut.rfind(" ")
        if space_index > int(limit * 0.5):
            return cut[:space_index].strip()
        return cut.strip()

    @staticmethod
    def _extract_steps(text: str) -> list[str]:
        chunks = re.split(r"[.\n]+", text)
        steps: list[str] = []
        for chunk in chunks:
            cleaned = " ".join(chunk.split())
            if cleaned:
                steps.append(cleaned)
            if len(steps) >= 5:
                break
        return steps
