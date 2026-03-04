"""Task lifecycle validation and transition logging."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class TaskState(str, Enum):
    """Allowed deterministic task states."""

    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


# Legacy compatibility transition matrix.
# Stage 13 lifecycle authority is intended to migrate to Rust IPC validation.
# This matrix is retained as fallback until router->Rust validation wiring is
# fully enabled across all execution paths.
LEGACY_ALLOWED_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.CREATED: {TaskState.ACTIVE, TaskState.ARCHIVED},
    TaskState.ACTIVE: {TaskState.COMPLETED, TaskState.ARCHIVED},
    TaskState.COMPLETED: {TaskState.ARCHIVED},
    TaskState.ARCHIVED: set(),
}


class InvalidStateTransitionError(ValueError):
    """Raised when a task transition violates lifecycle constraints."""


@dataclass(frozen=True)
class TransitionRecord:
    """Immutable audit event for task state transitions."""

    task_id: int
    from_state: TaskState
    to_state: TaskState
    changed_at_utc: datetime


@dataclass(frozen=True)
class LifecycleDecision:
    """Structured lifecycle authorization decision."""

    allowed: bool
    reason: str | None = None


TransitionAuthorizer = Callable[[int, TaskState, TaskState], LifecycleDecision | bool]


class LifecycleManager:
    """
    Deterministic task lifecycle manager.

    This module records transition events and delegates validation authority.
    It does not write to database state directly.
    """

    def __init__(
        self,
        *,
        transition_authorizer: TransitionAuthorizer | None = None,
        allow_legacy_fallback: bool = True,
    ) -> None:
        self._transition_log: list[TransitionRecord] = []
        self._transition_authorizer = transition_authorizer
        self._allow_legacy_fallback = bool(allow_legacy_fallback)

    def set_transition_authorizer(self, authorizer: TransitionAuthorizer | None) -> None:
        """Inject or clear external lifecycle authorizer."""
        self._transition_authorizer = authorizer

    @staticmethod
    def normalize_state(state: str | TaskState) -> TaskState:
        """Normalize incoming string/enum state to TaskState."""
        if isinstance(state, TaskState):
            return state
        try:
            return TaskState(state)
        except ValueError as exc:
            raise InvalidStateTransitionError(f"Unknown task state: {state!r}") from exc

    def can_transition(self, from_state: str | TaskState, to_state: str | TaskState) -> bool:
        """Return whether a transition is authorized."""
        src = self.normalize_state(from_state)
        dst = self.normalize_state(to_state)
        decision = self._authorize_transition(task_id=0, from_state=src, to_state=dst)
        return decision.allowed

    def assert_transition(
        self,
        task_id: int,
        from_state: str | TaskState,
        to_state: str | TaskState,
    ) -> None:
        """Authorize transition and append transition audit record."""
        src = self.normalize_state(from_state)
        dst = self.normalize_state(to_state)

        decision = self._authorize_transition(task_id=task_id, from_state=src, to_state=dst)
        if not decision.allowed:
            reason = f" ({decision.reason})" if decision.reason else ""
            raise InvalidStateTransitionError(
                f"Invalid transition for task {task_id}: {src.value} -> {dst.value}{reason}"
            )
        self._append_transition_record(task_id=task_id, from_state=src, to_state=dst)

    def record_transition(
        self,
        task_id: int,
        from_state: str | TaskState,
        to_state: str | TaskState,
    ) -> None:
        """
        Record an already-authorized transition without local validation.

        Stage 16 uses this path when Rust memory authority has already approved
        the transition.
        """
        src = self.normalize_state(from_state)
        dst = self.normalize_state(to_state)
        self._append_transition_record(task_id=task_id, from_state=src, to_state=dst)

    def get_transition_log(self) -> tuple[TransitionRecord, ...]:
        """Return immutable transition history for audit/testing."""
        return tuple(self._transition_log)

    def _authorize_transition(
        self,
        *,
        task_id: int,
        from_state: TaskState,
        to_state: TaskState,
    ) -> LifecycleDecision:
        if self._transition_authorizer is not None:
            raw_result = self._transition_authorizer(task_id, from_state, to_state)
            if isinstance(raw_result, LifecycleDecision):
                return raw_result
            if isinstance(raw_result, bool):
                return LifecycleDecision(
                    allowed=raw_result,
                    reason=None if raw_result else "EXTERNAL_DENIED",
                )
            return LifecycleDecision(allowed=False, reason="EXTERNAL_INVALID_RESULT")

        if self._allow_legacy_fallback:
            allowed = to_state in LEGACY_ALLOWED_TRANSITIONS[from_state]
            return LifecycleDecision(
                allowed=allowed,
                reason=None if allowed else "LEGACY_INVALID_TRANSITION",
            )

        return LifecycleDecision(allowed=False, reason="LIFECYCLE_AUTH_UNAVAILABLE")

    def _append_transition_record(
        self,
        *,
        task_id: int,
        from_state: TaskState,
        to_state: TaskState,
    ) -> None:
        record = TransitionRecord(
            task_id=task_id,
            from_state=from_state,
            to_state=to_state,
            changed_at_utc=datetime.now(timezone.utc),
        )
        self._transition_log.append(record)
        logger.info(
            "Task lifecycle transition accepted task_id=%s from=%s to=%s",
            task_id,
            from_state.value,
            to_state.value,
        )
