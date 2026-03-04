"""Deterministic replay fixture for certification harness."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Iterable
from unittest.mock import patch

from core.cognition.challenge_logic import ChallengeLogic
from core.cognition.command_router import CommandResult, CommandRouter
from core.cognition.reasoning_engine import ReasoningEngine, StructuredReasoningOutput
from core.connectors.mobile_connector import MobileConnector
from core.memory.lifecycle_manager import LifecycleManager
from core.memory.task_store import TaskStore
from services.sync_daemon import SyncDaemon


@dataclass(frozen=True)
class ReplayEvent:
    """Immutable deterministic replay event descriptor."""

    event_type: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class ReplayRunOutput:
    """Canonical output captured from one replay pass."""

    ipc_envelopes: tuple[dict[str, Any], ...]
    router_results: tuple[dict[str, Any], ...]
    reasoning_outputs: tuple[dict[str, Any], ...]
    lifecycle_transitions: tuple[dict[str, Any], ...]
    task_states: tuple[dict[str, Any], ...]

    def stable_hash(self) -> str:
        encoded = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class CaptureBridge:
    """Deterministic in-memory sink for connector envelopes."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def publish_event(self, message: dict[str, Any]) -> None:
        self.messages.append(json.loads(json.dumps(message, sort_keys=True)))

    def send_message(self, message: dict[str, Any]) -> None:
        self.publish_event(message)


class DeterministicClock:
    """Monotonic deterministic clock callable used for connector timestamps."""

    def __init__(self, *, start_seconds: float = 1_700_000_000.0, tick_seconds: float = 0.01) -> None:
        self._value = float(start_seconds)
        self._tick = float(tick_seconds)

    def __call__(self) -> float:
        current = self._value
        self._value += self._tick
        return current


SCENARIO_EVENTS: tuple[ReplayEvent, ...] = (
    ReplayEvent(event_type="energy_change", payload={"battery_percent": 60}),
    ReplayEvent(
        event_type="mobile_event",
        payload={
            "action": "create_task",
            "payload": {
                "task": "Replay certification task",
                "goal": "deterministic replay",
                "priority": 1,
            },
            "correlation_id": "replay-mobile-1",
        },
    ),
    ReplayEvent(
        event_type="sync_update",
        payload={
            "source_id": "mobile-a",
            "sync_type": "TASK_UPDATE",
            "payload": {"external_task_id": "ext-1", "state": "pending"},
            "timestamp": 1_700_000_100,
            "correlation_id": "replay-sync-1",
            "merge_hint": {
                "source_priority": "normal",
                "version": "v1",
                "external_timestamp": 1_700_000_100,
            },
        },
    ),
    ReplayEvent(event_type="energy_change", payload={"battery_percent": 30}),
    ReplayEvent(
        event_type="voice_command",
        payload={
            "query": "Plan deterministic replay validation",
            "correlation_id": "replay-voice-1",
        },
    ),
    ReplayEvent(
        event_type="mobile_event",
        payload={
            "action": "complete_task",
            "payload": {
                "task_id": 1,
                "alignment_score": 1.0,
                "declared_goal": "deterministic replay",
            },
            "correlation_id": "replay-mobile-2",
        },
    ),
    ReplayEvent(
        event_type="mobile_event",
        payload={
            "action": "archive_task",
            "payload": {
                "task_id": 1,
                "alignment_score": 1.0,
                "declared_goal": "deterministic replay",
            },
            "correlation_id": "replay-mobile-3",
        },
    ),
    ReplayEvent(
        event_type="sync_update",
        payload={
            "source_id": "laptop-b",
            "sync_type": "ARCHIVAL_HINT",
            "payload": {"external_task_id": "ext-1", "state": "archived"},
            "timestamp": 1_700_000_101,
            "correlation_id": "replay-sync-2",
            "merge_hint": {
                "source_priority": "high",
                "version": "v2",
                "external_timestamp": 1_700_000_101,
            },
        },
    ),
)


def _energy_mode(battery_percent: int) -> str:
    if battery_percent >= 50:
        return "STRATEGIC"
    if battery_percent >= 20:
        return "REDUCED"
    return "SILENT"


def _intent_timestamp(index: int) -> str:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return (base + timedelta(seconds=index)).isoformat()


def _build_intent(event: ReplayEvent, index: int) -> dict[str, Any]:
    action = str(event.payload["action"]).strip().lower()
    payload = dict(event.payload["payload"])
    entities: dict[str, Any]

    if action == "create_task":
        entities = {
            "task": payload.get("task", ""),
            "goal": payload.get("goal"),
            "priority": int(payload.get("priority", 0)),
        }
    else:
        entities = {
            "task_id": int(payload["task_id"]),
            "alignment_score": float(payload.get("alignment_score", 1.0)),
            "declared_goal": str(payload.get("declared_goal", "")),
        }

    return {
        "intent_id": f"replay-intent-{index}",
        "intent_type": action,
        "entities": entities,
        "timestamp": _intent_timestamp(index),
        "confidence_score": 0.99,
    }


def _normalize_router_result(result: CommandResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "action": result.action,
        "message_key": result.message_key,
        "error_code": result.error_code,
        "metadata": dict(result.metadata),
        "challenge_required": result.challenge_payload is not None,
    }


def _normalize_reasoning(output: StructuredReasoningOutput, correlation_id: str) -> dict[str, Any]:
    payload = {
        "correlation_id": correlation_id,
        "summary": output.summary,
        "strategy_steps": list(output.strategy_steps),
        "safe_to_present": output.safe_to_present,
        "blocked_reason": output.blocked_reason,
    }
    payload["structure_keys"] = sorted(payload.keys())
    return payload


def _collect_transitions(lifecycle: LifecycleManager) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for record in lifecycle.get_transition_log():
        rows.append(
            {
                "task_id": record.task_id,
                "from_state": record.from_state.value,
                "to_state": record.to_state.value,
            }
        )
    return tuple(rows)


def _collect_task_states(store: TaskStore) -> tuple[dict[str, Any], ...]:
    records = store.list_tasks(include_archived=True)
    return tuple(
        {
            "task_id": item.task_id,
            "title": item.title,
            "state": item.state.value,
            "priority": item.priority,
        }
        for item in records
    )


def _run_events(events: Iterable[ReplayEvent]) -> ReplayRunOutput:
    bridge = CaptureBridge()
    lifecycle = LifecycleManager()
    store = TaskStore(lifecycle_manager=lifecycle)
    router = CommandRouter(
        task_store=store,
        lifecycle_manager=lifecycle,
        challenge_logic=ChallengeLogic(),
        config_path="configs/default.yaml",
    )
    connector = MobileConnector(bridge)
    sync_daemon = SyncDaemon(bridge)
    reasoning = ReasoningEngine()

    router_results: list[dict[str, Any]] = []
    reasoning_outputs: list[dict[str, Any]] = []
    battery_percent = 60

    clock = DeterministicClock()
    with patch("core.connectors.mobile_connector.time.time", new=clock):
        for index, event in enumerate(events):
            if event.event_type == "energy_change":
                battery_percent = int(event.payload["battery_percent"])
                continue

            if event.event_type == "mobile_event":
                connector.receive_event(event.payload)
                intent = _build_intent(event, index)
                route_result = router.route(intent)
                router_results.append(_normalize_router_result(route_result))
                continue

            if event.event_type == "sync_update":
                sync_daemon.receive_sync(event.payload)
                continue

            if event.event_type == "voice_command":
                low_energy = _energy_mode(battery_percent) != "STRATEGIC"
                context = {
                    "goal": str(event.payload.get("query", "")),
                    "notes": str(event.payload.get("query", "")),
                    "horizon_days": 7,
                    "low_energy": low_energy,
                }
                output = reasoning.generate_strategy(context)
                reasoning_outputs.append(
                    _normalize_reasoning(output, str(event.payload.get("correlation_id", "voice")))
                )
                continue

            raise ValueError(f"Unsupported replay event type: {event.event_type}")

    try:
        return ReplayRunOutput(
            ipc_envelopes=tuple(bridge.messages),
            router_results=tuple(router_results),
            reasoning_outputs=tuple(reasoning_outputs),
            lifecycle_transitions=_collect_transitions(lifecycle),
            task_states=_collect_task_states(store),
        )
    finally:
        store.close()


def run_replay_capture() -> ReplayRunOutput:
    """Execute deterministic replay scenario once and capture canonical output."""
    return _run_events(SCENARIO_EVENTS)


def run_replay_twice() -> tuple[ReplayRunOutput, ReplayRunOutput]:
    """Execute replay scenario twice for deterministic equivalence checks."""
    return (run_replay_capture(), run_replay_capture())
