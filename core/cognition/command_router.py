"""Deterministic command routing boundary for APCOS cognitive actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Mapping
from uuid import uuid4

try:
    import yaml
except ImportError:  # pragma: no cover - covered indirectly via fallback behavior
    yaml = None

from core.cognition.challenge_logic import ChallengeLogic
from core.memory.lifecycle_manager import InvalidStateTransitionError, LifecycleManager, TaskState
from core.memory.task_store import TaskRecord, TaskStore

logger = logging.getLogger(__name__)

CommandStatus = str
ActionHandler = Callable[[dict[str, Any]], "ActionExecution"]
EntityValidator = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class CommandResult:
    """Structured command router output contract."""

    status: CommandStatus
    action: str
    audit_id: str
    message_key: str
    metadata: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    challenge_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class ActionExecution:
    """Structured internal action execution result."""

    action_type: str
    lifecycle_before: str | None
    lifecycle_after: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionDefinition:
    """Declarative action registration entry."""

    action_type: str
    handler: ActionHandler
    validator: EntityValidator
    challengeable: bool


class CommandRouter:
    """
    Single deterministic gateway between structured intents and cognitive actions.

    Responsibilities:
    - validate intent shape and confidence
    - map intent type to declarative action handlers
    - run advisory challenge hook for sensitive actions
    - return structured execution outcomes
    - emit audit events via logging
    """

    REQUIRED_INTENT_KEYS = ("intent_type", "entities", "timestamp", "confidence_score")

    def __init__(
        self,
        *,
        task_store: TaskStore,
        lifecycle_manager: LifecycleManager,
        challenge_logic: ChallengeLogic | None = None,
        config_path: str | Path = "configs/default.yaml",
    ) -> None:
        self._task_store = task_store
        self._lifecycle = lifecycle_manager
        self._challenge_logic = challenge_logic or ChallengeLogic()
        self._config_path = Path(config_path)

        settings = self._load_settings(self._config_path)
        self._min_confidence = float(settings["min_confidence"])
        self._enable_challenge_gate = bool(settings["enable_challenge_gate"])

        self._registry: dict[str, ActionDefinition] = {}
        self._audit_events: list[dict[str, Any]] = []
        self._lock = RLock()
        self._register_default_handlers()

    def route(self, intent_object: dict[str, Any]) -> CommandResult:
        """
        Route a single intent into one deterministic action result.

        This is the only execution entrypoint.
        """
        audit_id = str(uuid4())

        try:
            intent = self._validate_and_normalize_intent(intent_object)
        except ValueError:
            result = CommandResult(
                status="rejected",
                action="UNKNOWN",
                audit_id=audit_id,
                message_key="COMMAND_REJECTED",
                error_code="INVALID_INTENT_SHAPE",
                metadata={},
            )
            self._emit_audit_event(
                audit_id=audit_id,
                intent_id=intent_object.get("intent_id", "unknown"),
                intent_timestamp=self._safe_timestamp(intent_object.get("timestamp")),
                action_type=result.action,
                lifecycle_before=None,
                lifecycle_after=None,
                success_flag=False,
                entities=self._safe_entities_for_audit(intent_object.get("entities")),
            )
            return result

        if intent["confidence_score"] < self._min_confidence:
            result = CommandResult(
                status="rejected",
                action="UNKNOWN",
                audit_id=audit_id,
                message_key="COMMAND_REJECTED",
                error_code="LOW_CONFIDENCE",
                metadata={"min_confidence": self._min_confidence},
            )
            self._emit_audit_event(
                audit_id=audit_id,
                intent_id=intent["intent_id"],
                intent_timestamp=intent["timestamp"],
                action_type=result.action,
                lifecycle_before=None,
                lifecycle_after=None,
                success_flag=False,
                entities=self._safe_entities_for_audit(intent["entities"]),
            )
            return result

        definition = self._registry.get(intent["intent_type"])
        if definition is None:
            result = CommandResult(
                status="rejected",
                action="UNKNOWN",
                audit_id=audit_id,
                message_key="COMMAND_REJECTED",
                error_code="UNSUPPORTED_INTENT",
                metadata={"intent_type": intent["intent_type"]},
            )
            self._emit_audit_event(
                audit_id=audit_id,
                intent_id=intent["intent_id"],
                intent_timestamp=intent["timestamp"],
                action_type=result.action,
                lifecycle_before=None,
                lifecycle_after=None,
                success_flag=False,
                entities=self._safe_entities_for_audit(intent["entities"]),
            )
            return result

        try:
            definition.validator(intent["entities"])
        except ValueError:
            result = CommandResult(
                status="rejected",
                action=definition.action_type,
                audit_id=audit_id,
                message_key="COMMAND_REJECTED",
                error_code="INVALID_ENTITY",
                metadata={},
            )
            self._emit_audit_event(
                audit_id=audit_id,
                intent_id=intent["intent_id"],
                intent_timestamp=intent["timestamp"],
                action_type=definition.action_type,
                lifecycle_before=None,
                lifecycle_after=None,
                success_flag=False,
                entities=self._safe_entities_for_audit(intent["entities"]),
            )
            return result

        challenge_payload = self._evaluate_challenge(intent, definition)
        if challenge_payload is not None:
            result = CommandResult(
                status="challenge_required",
                action=definition.action_type,
                audit_id=audit_id,
                message_key="CHALLENGE_REQUIRED",
                challenge_payload=challenge_payload,
                metadata={},
            )
            self._emit_audit_event(
                audit_id=audit_id,
                intent_id=intent["intent_id"],
                intent_timestamp=intent["timestamp"],
                action_type=definition.action_type,
                lifecycle_before=None,
                lifecycle_after=None,
                success_flag=False,
                entities=self._safe_entities_for_audit(intent["entities"]),
            )
            return result

        try:
            execution = definition.handler(intent["entities"])
            result = CommandResult(
                status="executed",
                action=execution.action_type,
                audit_id=audit_id,
                message_key="COMMAND_EXECUTED",
                metadata=execution.metadata,
            )
            self._emit_audit_event(
                audit_id=audit_id,
                intent_id=intent["intent_id"],
                intent_timestamp=intent["timestamp"],
                action_type=execution.action_type,
                lifecycle_before=execution.lifecycle_before,
                lifecycle_after=execution.lifecycle_after,
                success_flag=True,
                entities=self._safe_entities_for_audit(intent["entities"]),
            )
            return result
        except InvalidStateTransitionError:
            result = CommandResult(
                status="rejected",
                action=definition.action_type,
                audit_id=audit_id,
                message_key="COMMAND_REJECTED",
                error_code="INVALID_TRANSITION",
                metadata={},
            )
            self._emit_audit_event(
                audit_id=audit_id,
                intent_id=intent["intent_id"],
                intent_timestamp=intent["timestamp"],
                action_type=definition.action_type,
                lifecycle_before=None,
                lifecycle_after=None,
                success_flag=False,
                entities=self._safe_entities_for_audit(intent["entities"]),
            )
            return result
        except (KeyError, TypeError, ValueError):
            result = CommandResult(
                status="rejected",
                action=definition.action_type,
                audit_id=audit_id,
                message_key="COMMAND_REJECTED",
                error_code="INVALID_ENTITY",
                metadata={},
            )
            self._emit_audit_event(
                audit_id=audit_id,
                intent_id=intent["intent_id"],
                intent_timestamp=intent["timestamp"],
                action_type=definition.action_type,
                lifecycle_before=None,
                lifecycle_after=None,
                success_flag=False,
                entities=self._safe_entities_for_audit(intent["entities"]),
            )
            return result
        except Exception:
            result = CommandResult(
                status="rejected",
                action=definition.action_type,
                audit_id=audit_id,
                message_key="COMMAND_REJECTED",
                error_code="INTERNAL_ERROR",
                metadata={},
            )
            self._emit_audit_event(
                audit_id=audit_id,
                intent_id=intent["intent_id"],
                intent_timestamp=intent["timestamp"],
                action_type=definition.action_type,
                lifecycle_before=None,
                lifecycle_after=None,
                success_flag=False,
                entities=self._safe_entities_for_audit(intent["entities"]),
            )
            return result

    def register_action_handler(
        self,
        intent_type: str,
        handler: ActionHandler,
        *,
        action_type: str | None = None,
        validator: EntityValidator | None = None,
        challengeable: bool = False,
    ) -> None:
        """Register an intent handler for future extensibility."""
        normalized_intent = self._normalize_intent_type(intent_type)
        with self._lock:
            self._registry[normalized_intent] = ActionDefinition(
                action_type=(action_type or normalized_intent.upper()),
                handler=handler,
                validator=validator or self._validate_passthrough,
                challengeable=challengeable,
            )

    def get_audit_events(self) -> tuple[dict[str, Any], ...]:
        """Return immutable audit event snapshot for testing/audit checks."""
        with self._lock:
            return tuple(self._audit_events)

    def _register_default_handlers(self) -> None:
        self.register_action_handler(
            "create_task",
            self._handle_create_task,
            action_type="CREATE_TASK",
            validator=self._validate_create_task_entities,
            challengeable=False,
        )
        self.register_action_handler(
            "schedule_task",
            self._handle_create_task,
            action_type="CREATE_TASK",
            validator=self._validate_create_task_entities,
            challengeable=False,
        )
        self.register_action_handler(
            "complete_task",
            self._handle_complete_task,
            action_type="COMPLETE_TASK",
            validator=self._validate_task_reference_entities,
            challengeable=True,
        )
        self.register_action_handler(
            "mark_completed",
            self._handle_complete_task,
            action_type="COMPLETE_TASK",
            validator=self._validate_task_reference_entities,
            challengeable=True,
        )
        self.register_action_handler(
            "cancel_task",
            self._handle_cancel_task,
            action_type="CANCEL_TASK",
            validator=self._validate_task_reference_entities,
            challengeable=True,
        )
        self.register_action_handler(
            "archive_task",
            self._handle_cancel_task,
            action_type="CANCEL_TASK",
            validator=self._validate_task_reference_entities,
            challengeable=True,
        )

    def _validate_and_normalize_intent(self, intent_object: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(intent_object, Mapping):
            raise ValueError("Intent must be a mapping")

        missing = [field for field in self.REQUIRED_INTENT_KEYS if field not in intent_object]
        if missing:
            raise ValueError(f"Missing required intent fields: {missing}")

        intent_type = self._normalize_intent_type(intent_object["intent_type"])
        entities = intent_object["entities"]
        if not isinstance(entities, Mapping):
            raise ValueError("entities must be a mapping")

        confidence = intent_object["confidence_score"]
        if not isinstance(confidence, (float, int)):
            raise ValueError("confidence_score must be numeric")
        confidence_float = float(confidence)
        if confidence_float < 0.0 or confidence_float > 1.0:
            raise ValueError("confidence_score must be in [0.0, 1.0]")

        return {
            "intent_id": str(intent_object.get("intent_id", uuid4())),
            "intent_type": intent_type,
            "entities": dict(entities),
            "timestamp": self._normalize_timestamp(intent_object["timestamp"]),
            "confidence_score": confidence_float,
        }

    @staticmethod
    def _normalize_intent_type(intent_type: Any) -> str:
        if not isinstance(intent_type, str) or not intent_type.strip():
            raise ValueError("intent_type must be a non-empty string")
        return intent_type.strip().lower()

    @staticmethod
    def _normalize_timestamp(timestamp: Any) -> str:
        if isinstance(timestamp, datetime):
            value = timestamp
        elif isinstance(timestamp, str):
            value = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        else:
            raise ValueError("timestamp must be ISO string or datetime")
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _safe_timestamp(timestamp: Any) -> str:
        try:
            return CommandRouter._normalize_timestamp(timestamp)
        except ValueError:
            return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _validate_passthrough(_: dict[str, Any]) -> None:
        return

    @staticmethod
    def _validate_create_task_entities(entities: dict[str, Any]) -> None:
        title = entities.get("task", entities.get("title"))
        if not isinstance(title, str) or not title.strip():
            raise ValueError("create_task requires non-empty task/title")

        due_at = entities.get("due_at")
        if due_at is not None and (not isinstance(due_at, str) or not due_at.strip()):
            raise ValueError("due_at must be an ISO string when supplied")
        if isinstance(due_at, str):
            CommandRouter._normalize_timestamp(due_at)

        priority = entities.get("priority")
        if priority is not None and not isinstance(priority, int):
            raise ValueError("priority must be integer")

    @staticmethod
    def _validate_task_reference_entities(entities: dict[str, Any]) -> None:
        task_id = entities.get("task_id")
        task_name = entities.get("task")
        if task_id is None and (not isinstance(task_name, str) or not task_name.strip()):
            raise ValueError("task_id or task is required")
        if task_id is not None and (not isinstance(task_id, int) or task_id <= 0):
            raise ValueError("task_id must be a positive integer")

        alignment = entities.get("alignment_score")
        if alignment is not None:
            if not isinstance(alignment, (float, int)):
                raise ValueError("alignment_score must be numeric")
            if float(alignment) < 0.0 or float(alignment) > 1.0:
                raise ValueError("alignment_score must be in [0.0, 1.0]")

    def _handle_create_task(self, entities: dict[str, Any]) -> ActionExecution:
        title = entities.get("task", entities.get("title"))
        record = self._task_store.create_task(
            title=title,
            description=entities.get("description"),
            due_at=entities.get("due_at"),
            goal=entities.get("goal"),
            priority=int(entities.get("priority", 0)),
        )
        # Validate deterministic initial lifecycle state.
        state = self._lifecycle.normalize_state(record.state)
        if state != TaskState.CREATED:
            raise InvalidStateTransitionError("New task must begin in CREATED state")
        return ActionExecution(
            action_type="CREATE_TASK",
            lifecycle_before=None,
            lifecycle_after=record.state.value,
            metadata={"task_id": record.task_id},
        )

    def _handle_complete_task(self, entities: dict[str, Any]) -> ActionExecution:
        task = self._resolve_task_reference(entities)
        before = task.state.value
        if task.state == TaskState.COMPLETED:
            return ActionExecution(
                action_type="COMPLETE_TASK",
                lifecycle_before=before,
                lifecycle_after=before,
                metadata={"task_id": task.task_id, "idempotent": True},
            )
        updated = self._task_store.complete_task(task.task_id)
        return ActionExecution(
            action_type="COMPLETE_TASK",
            lifecycle_before=before,
            lifecycle_after=updated.state.value,
            metadata={"task_id": task.task_id},
        )

    def _handle_cancel_task(self, entities: dict[str, Any]) -> ActionExecution:
        task = self._resolve_task_reference(entities)
        before = task.state.value
        if task.state == TaskState.ARCHIVED:
            return ActionExecution(
                action_type="CANCEL_TASK",
                lifecycle_before=before,
                lifecycle_after=before,
                metadata={"task_id": task.task_id, "idempotent": True},
            )
        updated = self._task_store.archive_task(task.task_id)
        return ActionExecution(
            action_type="CANCEL_TASK",
            lifecycle_before=before,
            lifecycle_after=updated.state.value,
            metadata={"task_id": task.task_id},
        )

    def _resolve_task_reference(self, entities: Mapping[str, Any]) -> TaskRecord:
        task_id = entities.get("task_id")
        if isinstance(task_id, int):
            task = self._task_store.get_task(task_id)
            if task is None:
                raise KeyError(f"task_id {task_id} not found")
            return task

        task_name = str(entities.get("task", "")).strip().lower()
        if not task_name:
            raise ValueError("Task reference not provided")

        matches = [
            task
            for task in self._task_store.list_tasks(include_archived=True)
            if task.title.lower() == task_name
        ]
        if not matches:
            raise KeyError("Task not found")
        if len(matches) > 1:
            raise ValueError("Ambiguous task reference")
        return matches[0]

    def _evaluate_challenge(
        self,
        intent: Mapping[str, Any],
        definition: ActionDefinition,
    ) -> dict[str, Any] | None:
        if not self._enable_challenge_gate or not definition.challengeable:
            return None

        entities = intent["entities"]
        try:
            task = self._resolve_task_reference(entities)
        except (KeyError, ValueError):
            return None

        alignment_score = float(entities.get("alignment_score", 1.0))
        declared_goal = str(entities.get("declared_goal", task.goal or ""))
        proposed_action = definition.action_type.lower()

        return self._challenge_logic.evaluate(
            task_id=task.task_id,
            proposed_action=proposed_action,
            declared_goal=declared_goal,
            alignment_score=alignment_score,
            user_overrode=bool(entities.get("user_overrode", False)),
        )

    def _emit_audit_event(
        self,
        *,
        audit_id: str,
        intent_id: str,
        intent_timestamp: str,
        action_type: str,
        lifecycle_before: str | None,
        lifecycle_after: str | None,
        success_flag: bool,
        entities: dict[str, Any],
    ) -> None:
        event = {
            "audit_id": audit_id,
            "intent_id": intent_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "intent_timestamp": intent_timestamp,
            "identity_tier": "TIER_UNKNOWN",
            "action_type": action_type,
            "lifecycle_before": lifecycle_before,
            "lifecycle_after": lifecycle_after,
            "success_flag": success_flag,
            "entities": entities,
        }
        with self._lock:
            self._audit_events.append(event)
        logger.info("command_router_audit_event=%s", event)

    @staticmethod
    def _safe_entities_for_audit(entities: Any) -> dict[str, Any]:
        if not isinstance(entities, Mapping):
            return {}
        if bool(entities.get("sensitive", False)):
            return {
                "sensitive": True,
                "entity_keys": sorted(str(key) for key in entities.keys()),
            }
        return dict(entities)

    @staticmethod
    def _load_settings(config_path: Path) -> dict[str, Any]:
        defaults = {
            "min_confidence": 0.65,
            "enable_challenge_gate": True,
        }
        if not config_path.exists():
            return defaults

        if yaml is None:
            return defaults

        with config_path.open("r", encoding="utf-8") as handle:
            parsed = yaml.safe_load(handle) or {}
        router_cfg = parsed.get("command_router", {})
        if not isinstance(router_cfg, Mapping):
            return defaults
        return {
            "min_confidence": router_cfg.get("min_confidence", defaults["min_confidence"]),
            "enable_challenge_gate": router_cfg.get(
                "enable_challenge_gate",
                defaults["enable_challenge_gate"],
            ),
        }
