"""Mobile connector adapter for controlled external event ingress."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import Any, Mapping
from uuid import uuid4

from services.ipc.rust_bridge import MESSAGE_EVENT

logger = logging.getLogger(__name__)

FORBIDDEN_PAYLOAD_KEYS = {"__class__", "__dict__", "__globals__"}


@dataclass(frozen=True)
class EventEnvelope:
    """Normalized external event representation."""

    event_type: str
    payload: dict[str, Any]
    source: str
    timestamp: int
    correlation_id: str


class MobileConnector:
    """
    Thin adapter that translates mobile events to internal IPC event envelopes.

    This component is intentionally stateless and does not mutate memory or
    execute any authority decisions.
    """

    ACTION_EVENT_MAP: dict[str, str] = {
        "create_task": "TaskCreated",
        "complete_task": "TaskCompleted",
        "archive_task": "TaskArchived",
        "cancel_task": "TaskArchived",
        "reminder_ack": "LifecycleValidated",
    }
    REQUIRED_KEYS = ("action", "payload")

    def __init__(self, ipc_bridge: Any, *, source: str = "mobile") -> None:
        self._bridge = ipc_bridge
        self._source = source

    def receive_event(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """
        Validate and forward one external event through IPC.

        Returns the serialized IPC envelope sent to the bridge.
        """
        envelope = self._normalize_event(payload)
        message = {
            "message_type": MESSAGE_EVENT,
            "timestamp": envelope.timestamp,
            "correlation_id": envelope.correlation_id,
            "payload": {
                "event": envelope.event_type,
                "data": {
                    "source": envelope.source,
                    "payload": envelope.payload,
                },
            },
        }
        self._publish(message)
        logger.debug(
            "mobile_connector_forwarded event=%s correlation_id=%s",
            envelope.event_type,
            envelope.correlation_id,
        )
        return message

    def _normalize_event(self, payload: Mapping[str, Any]) -> EventEnvelope:
        validated = self._validate_payload(payload)
        action = str(validated["action"]).strip().lower()
        event_type = self.ACTION_EVENT_MAP[action]

        correlation_id = validated.get("correlation_id")
        if not isinstance(correlation_id, str) or not correlation_id.strip():
            correlation_id = f"mobile-{uuid4()}"

        return EventEnvelope(
            event_type=event_type,
            payload=dict(validated["payload"]),
            source=self._source,
            timestamp=int(time.time() * 1000),
            correlation_id=correlation_id.strip(),
        )

    def _validate_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise ValueError("INVALID_PAYLOAD_SHAPE")

        missing = [key for key in self.REQUIRED_KEYS if key not in payload]
        if missing:
            raise ValueError("MISSING_REQUIRED_FIELDS")

        action = payload.get("action")
        if not isinstance(action, str) or not action.strip():
            raise ValueError("INVALID_ACTION")
        normalized_action = action.strip().lower()
        if normalized_action not in self.ACTION_EVENT_MAP:
            raise ValueError("UNSUPPORTED_ACTION")

        body = payload.get("payload")
        if not isinstance(body, Mapping):
            raise ValueError("INVALID_PAYLOAD_BODY")

        unsafe_keys = [
            str(key)
            for key in body.keys()
            if str(key).startswith("__") or str(key) in FORBIDDEN_PAYLOAD_KEYS
        ]
        if unsafe_keys:
            raise ValueError("UNSAFE_PAYLOAD_KEY")

        correlation_id = payload.get("correlation_id")
        if correlation_id is not None and (
            not isinstance(correlation_id, str) or not correlation_id.strip()
        ):
            raise ValueError("INVALID_CORRELATION_ID")

        return {
            "action": normalized_action,
            "payload": dict(body),
            "correlation_id": correlation_id,
        }

    def _publish(self, message: dict[str, Any]) -> None:
        publish_fn = getattr(self._bridge, "publish_event", None)
        if callable(publish_fn):
            publish_fn(message)
            return

        send_fn = getattr(self._bridge, "send_message", None)
        if callable(send_fn):
            send_fn(message)
            return

        raise RuntimeError("IPC_BRIDGE_UNAVAILABLE")

