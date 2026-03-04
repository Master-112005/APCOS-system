"""Controlled synchronization coordinator for external state updates."""

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
class SyncEnvelope:
    """Normalized sync envelope passed to IPC."""

    source_id: str
    sync_type: str
    payload: dict[str, Any]
    timestamp: int
    correlation_id: str
    merge_hint: dict[str, Any]


class SyncDaemon:
    """
    Stateless sync coordinator that forwards external state suggestions via IPC.

    This service never performs memory transitions or storage mutations.
    """

    SYNC_EVENT_MAP: dict[str, str] = {
        "TASK_SNAPSHOT": "LifecycleValidated",
        "TASK_UPDATE": "TaskCreated",
        "VECTOR_UPDATE": "ModelDowngrade",
        "ARCHIVAL_HINT": "TaskArchived",
        "STATE_RECONCILE": "IdentityChanged",
    }
    REQUIRED_KEYS = ("source_id", "sync_type", "payload")

    def __init__(self, ipc_bridge: Any, *, source: str = "sync-daemon") -> None:
        self._bridge = ipc_bridge
        self._source = source

    def receive_sync(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """
        Validate and normalize one external sync payload, then forward via IPC.

        Returns serialized IPC envelope sent to the bridge.
        """
        envelope = self._normalize_payload(payload)
        message = {
            "message_type": MESSAGE_EVENT,
            "timestamp": envelope.timestamp,
            "correlation_id": envelope.correlation_id,
            "payload": {
                "event": self.SYNC_EVENT_MAP[envelope.sync_type],
                "data": {
                    "source": self._source,
                    "sync": {
                        "source_id": envelope.source_id,
                        "sync_type": envelope.sync_type,
                        "payload": envelope.payload,
                        "merge_hint": envelope.merge_hint,
                    },
                },
            },
        }
        self._publish(message)
        logger.debug(
            "sync_daemon_forwarded sync_type=%s source_id=%s correlation_id=%s",
            envelope.sync_type,
            envelope.source_id,
            envelope.correlation_id,
        )
        return message

    def _normalize_payload(self, payload: Mapping[str, Any]) -> SyncEnvelope:
        validated = self._validate_payload(payload)
        source_id = str(validated["source_id"]).strip()
        sync_type = str(validated["sync_type"]).strip().upper()
        body = dict(validated["payload"])
        provided_timestamp = validated["timestamp"]
        timestamp = int(provided_timestamp) if isinstance(provided_timestamp, (int, float)) else int(time.time() * 1000)
        correlation = validated["correlation_id"]
        if not isinstance(correlation, str) or not correlation.strip():
            correlation = f"sync-{uuid4()}"

        merge_hint = self._build_merge_hint(
            raw_hint=validated["merge_hint"],
            external_timestamp=timestamp,
        )
        return SyncEnvelope(
            source_id=source_id,
            sync_type=sync_type,
            payload=body,
            timestamp=timestamp,
            correlation_id=correlation.strip(),
            merge_hint=merge_hint,
        )

    def _validate_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise ValueError("INVALID_SYNC_PAYLOAD_SHAPE")

        missing = [key for key in self.REQUIRED_KEYS if key not in payload]
        if missing:
            raise ValueError("MISSING_REQUIRED_FIELDS")

        source_id = payload.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("INVALID_SOURCE_ID")

        sync_type = payload.get("sync_type")
        if not isinstance(sync_type, str) or not sync_type.strip():
            raise ValueError("INVALID_SYNC_TYPE")
        normalized_sync_type = sync_type.strip().upper()
        if normalized_sync_type not in self.SYNC_EVENT_MAP:
            raise ValueError("UNSUPPORTED_SYNC_TYPE")

        body = payload.get("payload")
        if not isinstance(body, Mapping):
            raise ValueError("INVALID_PAYLOAD_BODY")

        unsafe_payload_keys = [
            str(key)
            for key in body.keys()
            if str(key).startswith("__") or str(key) in FORBIDDEN_PAYLOAD_KEYS
        ]
        if unsafe_payload_keys:
            raise ValueError("UNSAFE_PAYLOAD_KEY")

        merge_hint = payload.get("merge_hint", {})
        if not isinstance(merge_hint, Mapping):
            raise ValueError("INVALID_MERGE_HINT")
        unsafe_merge_keys = [
            str(key)
            for key in merge_hint.keys()
            if str(key).startswith("__") or str(key) in FORBIDDEN_PAYLOAD_KEYS
        ]
        if unsafe_merge_keys:
            raise ValueError("UNSAFE_MERGE_HINT_KEY")

        timestamp = payload.get("timestamp")
        if timestamp is not None and not isinstance(timestamp, (int, float)):
            raise ValueError("INVALID_TIMESTAMP")

        correlation_id = payload.get("correlation_id")
        if correlation_id is not None and (
            not isinstance(correlation_id, str) or not correlation_id.strip()
        ):
            raise ValueError("INVALID_CORRELATION_ID")

        return {
            "source_id": source_id,
            "sync_type": normalized_sync_type,
            "payload": dict(body),
            "merge_hint": dict(merge_hint),
            "timestamp": timestamp,
            "correlation_id": correlation_id,
        }

    @staticmethod
    def _build_merge_hint(
        *,
        raw_hint: Mapping[str, Any],
        external_timestamp: int,
    ) -> dict[str, Any]:
        return {
            "source_priority": str(raw_hint.get("source_priority", "normal")),
            "version": str(raw_hint.get("version", "v1")),
            "external_timestamp": int(raw_hint.get("external_timestamp", external_timestamp)),
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

