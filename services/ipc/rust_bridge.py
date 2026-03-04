"""Minimal JSON-over-stdio bridge between Rust supervisor and Python runtime.

This bridge is intentionally thin and mutation-neutral. It accepts only
schema-validated envelopes and does not mutate memory directly.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import sys
import time
from typing import Any, Callable, TextIO

MESSAGE_EVENT = "EVENT"
MESSAGE_STATE_UPDATE = "STATE_UPDATE"
MESSAGE_AUTH_REQUEST = "AUTH_REQUEST"
MESSAGE_AUTH_RESULT = "AUTH_RESULT"
MESSAGE_TRANSITION_VALIDATE = "TRANSITION_VALIDATE"
MESSAGE_TRANSITION_RESULT = "TRANSITION_RESULT"
MESSAGE_ENERGY_VALIDATE = "ENERGY_VALIDATE"
MESSAGE_ENERGY_RESULT = "ENERGY_RESULT"
MESSAGE_STORAGE_VALIDATE = "STORAGE_VALIDATE"
MESSAGE_STORAGE_RESULT = "STORAGE_RESULT"
MESSAGE_MEMORY_VALIDATE = "MEMORY_VALIDATE"
MESSAGE_MEMORY_RESULT = "MEMORY_RESULT"
MAX_MESSAGE_BYTES = 64 * 1024
IPC_SCHEMA_VERSION = 1


def _timestamp_ms() -> int:
    return int(time.time() * 1000)


def _is_object(value: Any) -> bool:
    return isinstance(value, dict)


def parse_envelope(line: str, *, max_message_bytes: int = MAX_MESSAGE_BYTES) -> dict[str, Any] | None:
    """Parse and validate one IPC JSON envelope.

    Returns None for malformed, unsupported, or oversized payloads.
    """
    trimmed = line.strip()
    if not trimmed:
        return None
    if len(trimmed.encode("utf-8")) > max_message_bytes:
        return None
    try:
        payload = json.loads(trimmed)
    except json.JSONDecodeError:
        return None
    if not _is_object(payload):
        return None

    message_type = payload.get("message_type")
    timestamp = payload.get("timestamp")
    correlation_id = payload.get("correlation_id")
    body = payload.get("payload")

    if message_type not in {
        MESSAGE_EVENT,
        MESSAGE_STATE_UPDATE,
        MESSAGE_AUTH_REQUEST,
        MESSAGE_AUTH_RESULT,
        MESSAGE_TRANSITION_VALIDATE,
        MESSAGE_TRANSITION_RESULT,
        MESSAGE_ENERGY_VALIDATE,
        MESSAGE_ENERGY_RESULT,
        MESSAGE_STORAGE_VALIDATE,
        MESSAGE_STORAGE_RESULT,
        MESSAGE_MEMORY_VALIDATE,
        MESSAGE_MEMORY_RESULT,
    }:
        return None
    if not isinstance(timestamp, int):
        return None
    if not isinstance(correlation_id, str) or not correlation_id.strip():
        return None
    if not _is_object(body):
        return None
    return {
        "message_type": message_type,
        "timestamp": timestamp,
        "correlation_id": correlation_id,
        "payload": body,
    }


def build_state_update(
    *,
    correlation_id: str,
    component: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build deterministic STATE_UPDATE envelope."""
    payload: dict[str, Any] = {"component": component}
    if details:
        payload.update(details)
    return {
        "message_type": MESSAGE_STATE_UPDATE,
        "timestamp": _timestamp_ms(),
        "correlation_id": correlation_id,
        "payload": payload,
    }


def build_auth_request(
    *,
    correlation_id: str,
    user_id: str,
    tier: str,
    action: str,
    authenticated: bool,
) -> dict[str, Any]:
    """Build deterministic AUTH_REQUEST envelope."""
    return {
        "message_type": MESSAGE_AUTH_REQUEST,
        "timestamp": _timestamp_ms(),
        "correlation_id": correlation_id,
        "payload": {
            "user_id": user_id,
            "tier": tier,
            "action": action,
            "authenticated": bool(authenticated),
        },
    }


def build_auth_result(*, correlation_id: str, allowed: bool, reason: str | None) -> dict[str, Any]:
    """Build deterministic AUTH_RESULT envelope."""
    return {
        "message_type": MESSAGE_AUTH_RESULT,
        "timestamp": _timestamp_ms(),
        "correlation_id": correlation_id,
        "payload": {"allowed": bool(allowed), "reason": reason},
    }


def build_transition_validate(
    *,
    correlation_id: str,
    current_state: str,
    requested_state: str,
) -> dict[str, Any]:
    """Build deterministic TRANSITION_VALIDATE envelope."""
    return {
        "message_type": MESSAGE_TRANSITION_VALIDATE,
        "timestamp": _timestamp_ms(),
        "correlation_id": correlation_id,
        "payload": {
            "current_state": current_state,
            "requested_state": requested_state,
        },
    }


def build_transition_result(
    *, correlation_id: str, allowed: bool, reason: str | None
) -> dict[str, Any]:
    """Build deterministic TRANSITION_RESULT envelope."""
    return {
        "message_type": MESSAGE_TRANSITION_RESULT,
        "timestamp": _timestamp_ms(),
        "correlation_id": correlation_id,
        "payload": {"allowed": bool(allowed), "reason": reason},
    }


def build_energy_validate(
    *,
    correlation_id: str,
    battery_percent: int,
    execution_type: str,
) -> dict[str, Any]:
    """Build deterministic ENERGY_VALIDATE envelope."""
    return {
        "message_type": MESSAGE_ENERGY_VALIDATE,
        "timestamp": _timestamp_ms(),
        "correlation_id": correlation_id,
        "payload": {
            "battery_percent": int(battery_percent),
            "execution_type": execution_type,
        },
    }


def build_energy_result(
    *, correlation_id: str, allowed: bool, reason: str | None
) -> dict[str, Any]:
    """Build deterministic ENERGY_RESULT envelope."""
    return {
        "message_type": MESSAGE_ENERGY_RESULT,
        "timestamp": _timestamp_ms(),
        "correlation_id": correlation_id,
        "payload": {"allowed": bool(allowed), "reason": reason},
    }


def build_storage_validate(
    *,
    correlation_id: str,
    operation: str,
    lifecycle_state: str,
    energy_mode: str,
    execution_type: str,
    encryption_metadata_present: bool,
    encryption_key_id: str | None,
) -> dict[str, Any]:
    """Build deterministic STORAGE_VALIDATE envelope."""
    return {
        "message_type": MESSAGE_STORAGE_VALIDATE,
        "timestamp": _timestamp_ms(),
        "correlation_id": correlation_id,
        "payload": {
            "operation": operation,
            "lifecycle_state": lifecycle_state,
            "energy_mode": energy_mode,
            "execution_type": execution_type,
            "encryption_metadata_present": bool(encryption_metadata_present),
            "encryption_key_id": encryption_key_id,
        },
    }


def build_storage_result(
    *,
    correlation_id: str,
    allowed: bool,
    reason: str | None,
    retention_applied: bool,
    encryption_verified: bool,
) -> dict[str, Any]:
    """Build deterministic STORAGE_RESULT envelope."""
    return {
        "message_type": MESSAGE_STORAGE_RESULT,
        "timestamp": _timestamp_ms(),
        "correlation_id": correlation_id,
        "payload": {
            "allowed": bool(allowed),
            "reason": reason,
            "retention_applied": bool(retention_applied),
            "encryption_verified": bool(encryption_verified),
        },
    }


def build_memory_validate(
    *,
    correlation_id: str,
    current_lifecycle_state: str,
    operation: str,
    energy_mode: str,
    storage_permission_flag: bool,
    metadata_flags: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """Build deterministic MEMORY_VALIDATE envelope."""
    return {
        "message_type": MESSAGE_MEMORY_VALIDATE,
        "timestamp": _timestamp_ms(),
        "correlation_id": correlation_id,
        "payload": {
            "current_lifecycle_state": current_lifecycle_state,
            "operation": operation,
            "energy_mode": energy_mode,
            "storage_permission_flag": bool(storage_permission_flag),
            "metadata_flags": dict(metadata_flags or {}),
        },
    }


def build_memory_result(
    *,
    correlation_id: str,
    allowed: bool,
    reason: str | None,
    target_state: str | None,
    retention_applied: bool,
    tier_changed: bool,
) -> dict[str, Any]:
    """Build deterministic MEMORY_RESULT envelope."""
    return {
        "message_type": MESSAGE_MEMORY_RESULT,
        "timestamp": _timestamp_ms(),
        "correlation_id": correlation_id,
        "payload": {
            "allowed": bool(allowed),
            "reason": reason,
            "target_state": target_state,
            "retention_applied": bool(retention_applied),
            "tier_changed": bool(tier_changed),
        },
    }


def parse_auth_result(
    envelope: dict[str, Any], *, expected_correlation_id: str | None = None
) -> tuple[bool, str | None] | None:
    """Extract `(allowed, reason)` from a validated AUTH_RESULT envelope."""
    if envelope.get("message_type") != MESSAGE_AUTH_RESULT:
        return None
    if expected_correlation_id is not None and envelope.get("correlation_id") != expected_correlation_id:
        return None
    payload = envelope.get("payload")
    if not _is_object(payload):
        return None
    allowed = payload.get("allowed")
    reason = payload.get("reason")
    if not isinstance(allowed, bool):
        return None
    if reason is not None and not isinstance(reason, str):
        return None
    return (allowed, reason)


def parse_transition_result(
    envelope: dict[str, Any], *, expected_correlation_id: str | None = None
) -> tuple[bool, str | None] | None:
    """Extract `(allowed, reason)` from a validated TRANSITION_RESULT envelope."""
    if envelope.get("message_type") != MESSAGE_TRANSITION_RESULT:
        return None
    if expected_correlation_id is not None and envelope.get("correlation_id") != expected_correlation_id:
        return None
    payload = envelope.get("payload")
    if not _is_object(payload):
        return None
    allowed = payload.get("allowed")
    reason = payload.get("reason")
    if not isinstance(allowed, bool):
        return None
    if reason is not None and not isinstance(reason, str):
        return None
    return (allowed, reason)


def parse_energy_result(
    envelope: dict[str, Any], *, expected_correlation_id: str | None = None
) -> tuple[bool, str | None] | None:
    """Extract `(allowed, reason)` from a validated ENERGY_RESULT envelope."""
    if envelope.get("message_type") != MESSAGE_ENERGY_RESULT:
        return None
    if expected_correlation_id is not None and envelope.get("correlation_id") != expected_correlation_id:
        return None
    payload = envelope.get("payload")
    if not _is_object(payload):
        return None
    allowed = payload.get("allowed")
    reason = payload.get("reason")
    if not isinstance(allowed, bool):
        return None
    if reason is not None and not isinstance(reason, str):
        return None
    return (allowed, reason)


def parse_storage_result(
    envelope: dict[str, Any], *, expected_correlation_id: str | None = None
) -> tuple[bool, str | None, bool, bool] | None:
    """Extract storage decision fields from validated STORAGE_RESULT envelope."""
    if envelope.get("message_type") != MESSAGE_STORAGE_RESULT:
        return None
    if expected_correlation_id is not None and envelope.get("correlation_id") != expected_correlation_id:
        return None
    payload = envelope.get("payload")
    if not _is_object(payload):
        return None
    allowed = payload.get("allowed")
    reason = payload.get("reason")
    retention_applied = payload.get("retention_applied")
    encryption_verified = payload.get("encryption_verified")
    if not isinstance(allowed, bool):
        return None
    if reason is not None and not isinstance(reason, str):
        return None
    if not isinstance(retention_applied, bool):
        return None
    if not isinstance(encryption_verified, bool):
        return None
    return (allowed, reason, retention_applied, encryption_verified)


def parse_memory_result(
    envelope: dict[str, Any], *, expected_correlation_id: str | None = None
) -> tuple[bool, str | None, str | None, bool, bool] | None:
    """Extract memory decision fields from validated MEMORY_RESULT envelope."""
    if envelope.get("message_type") != MESSAGE_MEMORY_RESULT:
        return None
    if expected_correlation_id is not None and envelope.get("correlation_id") != expected_correlation_id:
        return None
    payload = envelope.get("payload")
    if not _is_object(payload):
        return None
    allowed = payload.get("allowed")
    reason = payload.get("reason")
    target_state = payload.get("target_state")
    retention_applied = payload.get("retention_applied")
    tier_changed = payload.get("tier_changed")
    if not isinstance(allowed, bool):
        return None
    if reason is not None and not isinstance(reason, str):
        return None
    if target_state is not None and not isinstance(target_state, str):
        return None
    if not isinstance(retention_applied, bool):
        return None
    if not isinstance(tier_changed, bool):
        return None
    return (allowed, reason, target_state, retention_applied, tier_changed)


@dataclass
class RustBridge:
    """Stateful bridge with loop suppression by correlation id."""

    in_stream: TextIO
    out_stream: TextIO
    event_handler: Callable[[dict[str, Any]], None] | None = None
    auth_transport: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None
    transition_transport: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None
    energy_transport: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None
    storage_transport: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None
    memory_transport: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None
    max_message_bytes: int = MAX_MESSAGE_BYTES

    def __post_init__(self) -> None:
        self._seen_correlation_ids: set[str] = set()

    def process_line(self, line: str) -> dict[str, Any] | None:
        """Handle one inbound line and optionally return outbound STATE_UPDATE."""
        envelope = parse_envelope(line, max_message_bytes=self.max_message_bytes)
        if envelope is None:
            return None

        correlation_id = str(envelope["correlation_id"])
        if correlation_id in self._seen_correlation_ids:
            return None
        self._seen_correlation_ids.add(correlation_id)

        if envelope["message_type"] == MESSAGE_STATE_UPDATE:
            # Never echo back a STATE_UPDATE to avoid IPC loops.
            return None
        if envelope["message_type"] == MESSAGE_AUTH_RESULT:
            # AUTH_RESULT is consumed by request_authorization() path.
            return None
        if envelope["message_type"] == MESSAGE_TRANSITION_RESULT:
            # TRANSITION_RESULT is consumed by request_transition_validation() path.
            return None
        if envelope["message_type"] == MESSAGE_ENERGY_RESULT:
            # ENERGY_RESULT is consumed by request_energy_validation() path.
            return None
        if envelope["message_type"] == MESSAGE_STORAGE_RESULT:
            # STORAGE_RESULT is consumed by request_storage_validation() path.
            return None
        if envelope["message_type"] == MESSAGE_MEMORY_RESULT:
            # MEMORY_RESULT is consumed by request_memory_validation() path.
            return None
        if envelope["message_type"] == MESSAGE_AUTH_REQUEST:
            # Python bridge does not authorize itself.
            return None
        if envelope["message_type"] == MESSAGE_TRANSITION_VALIDATE:
            # Python bridge does not validate transitions itself.
            return None
        if envelope["message_type"] == MESSAGE_ENERGY_VALIDATE:
            # Python bridge does not validate energy policy itself.
            return None
        if envelope["message_type"] == MESSAGE_STORAGE_VALIDATE:
            # Python bridge does not validate storage policy itself.
            return None
        if envelope["message_type"] == MESSAGE_MEMORY_VALIDATE:
            # Python bridge does not validate memory policy itself.
            return None

        event_payload = dict(envelope["payload"])
        if self.event_handler is not None:
            self.event_handler(event_payload)

        event_name = str(event_payload.get("event", "Unknown"))
        return build_state_update(
            correlation_id=correlation_id,
            component="RustBridge",
            details={"received_event": event_name, "status": "accepted"},
        )

    def request_authorization(
        self,
        *,
        user_id: str,
        tier: str,
        action: str,
        authenticated: bool,
        correlation_id: str,
    ) -> dict[str, Any]:
        """
        Request authorization from Rust authority.

        If no transport is configured or response is malformed, fail closed.
        """
        request = build_auth_request(
            correlation_id=correlation_id,
            user_id=user_id,
            tier=tier,
            action=action,
            authenticated=authenticated,
        )
        if self.auth_transport is None:
            return build_auth_result(
                correlation_id=correlation_id,
                allowed=False,
                reason="AUTH_UNAVAILABLE",
            )
        response = self.auth_transport(request)
        if not _is_object(response):
            return build_auth_result(
                correlation_id=correlation_id,
                allowed=False,
                reason="AUTH_INVALID_RESPONSE",
            )

        parsed = parse_auth_result(response, expected_correlation_id=correlation_id)
        if parsed is None:
            return build_auth_result(
                correlation_id=correlation_id,
                allowed=False,
                reason="AUTH_INVALID_RESPONSE",
            )
        allowed, reason = parsed
        return build_auth_result(
            correlation_id=correlation_id,
            allowed=allowed,
            reason=reason,
        )

    def request_transition_validation(
        self,
        *,
        current_state: str,
        requested_state: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """
        Request lifecycle transition validation from Rust authority.

        If no transport is configured or response is malformed, fail closed.
        """
        request = build_transition_validate(
            correlation_id=correlation_id,
            current_state=current_state,
            requested_state=requested_state,
        )
        transport = self.transition_transport or self.auth_transport
        if transport is None:
            return build_transition_result(
                correlation_id=correlation_id,
                allowed=False,
                reason="TRANSITION_AUTH_UNAVAILABLE",
            )
        response = transport(request)
        if not _is_object(response):
            return build_transition_result(
                correlation_id=correlation_id,
                allowed=False,
                reason="TRANSITION_INVALID_RESPONSE",
            )

        parsed = parse_transition_result(response, expected_correlation_id=correlation_id)
        if parsed is None:
            return build_transition_result(
                correlation_id=correlation_id,
                allowed=False,
                reason="TRANSITION_INVALID_RESPONSE",
            )
        allowed, reason = parsed
        return build_transition_result(
            correlation_id=correlation_id,
            allowed=allowed,
            reason=reason,
        )

    def authorize_and_maybe_route(
        self,
        *,
        user_id: str,
        tier: str,
        action: str,
        authenticated: bool,
        correlation_id: str,
        route_callable: Callable[[], Any],
    ) -> tuple[bool, Any | None, str | None]:
        """
        Authorize via Rust before calling router executor callback.
        """
        auth_result = self.request_authorization(
            user_id=user_id,
            tier=tier,
            action=action,
            authenticated=authenticated,
            correlation_id=correlation_id,
        )
        parsed = parse_auth_result(auth_result, expected_correlation_id=correlation_id)
        if parsed is None:
            return (False, None, "AUTH_INVALID_RESPONSE")
        allowed, reason = parsed
        if not allowed:
            return (False, None, reason or "ACCESS_DENIED")
        return (True, route_callable(), None)

    def validate_transition_and_maybe_route(
        self,
        *,
        current_state: str,
        requested_state: str,
        correlation_id: str,
        route_callable: Callable[[], Any],
    ) -> tuple[bool, Any | None, str | None]:
        """
        Validate transition via Rust before calling router executor callback.
        """
        transition_result = self.request_transition_validation(
            current_state=current_state,
            requested_state=requested_state,
            correlation_id=correlation_id,
        )
        parsed = parse_transition_result(
            transition_result, expected_correlation_id=correlation_id
        )
        if parsed is None:
            return (False, None, "TRANSITION_INVALID_RESPONSE")
        allowed, reason = parsed
        if not allowed:
            return (False, None, reason or "INVALID_TRANSITION")
        return (True, route_callable(), None)

    def request_energy_validation(
        self,
        *,
        battery_percent: int,
        execution_type: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """
        Request energy execution validation from Rust authority.

        If no transport is configured or response is malformed, fail closed.
        """
        request = build_energy_validate(
            correlation_id=correlation_id,
            battery_percent=battery_percent,
            execution_type=execution_type,
        )
        transport = self.energy_transport or self.auth_transport
        if transport is None:
            return build_energy_result(
                correlation_id=correlation_id,
                allowed=False,
                reason="ENERGY_AUTH_UNAVAILABLE",
            )
        response = transport(request)
        if not _is_object(response):
            return build_energy_result(
                correlation_id=correlation_id,
                allowed=False,
                reason="ENERGY_INVALID_RESPONSE",
            )
        parsed = parse_energy_result(response, expected_correlation_id=correlation_id)
        if parsed is None:
            return build_energy_result(
                correlation_id=correlation_id,
                allowed=False,
                reason="ENERGY_INVALID_RESPONSE",
            )
        allowed, reason = parsed
        return build_energy_result(
            correlation_id=correlation_id,
            allowed=allowed,
            reason=reason,
        )

    def validate_energy_and_maybe_execute(
        self,
        *,
        battery_percent: int,
        execution_type: str,
        correlation_id: str,
        execute_callable: Callable[[], Any],
    ) -> tuple[bool, Any | None, str | None]:
        """
        Validate energy policy via Rust before executing non-critical compute.
        """
        result = self.request_energy_validation(
            battery_percent=battery_percent,
            execution_type=execution_type,
            correlation_id=correlation_id,
        )
        parsed = parse_energy_result(result, expected_correlation_id=correlation_id)
        if parsed is None:
            return (False, None, "ENERGY_INVALID_RESPONSE")
        allowed, reason = parsed
        if not allowed:
            return (False, None, reason or "ENERGY_DENIED")
        return (True, execute_callable(), None)

    def request_storage_validation(
        self,
        *,
        operation: str,
        lifecycle_state: str,
        energy_mode: str,
        execution_type: str,
        encryption_metadata_present: bool,
        encryption_key_id: str | None,
        correlation_id: str,
    ) -> dict[str, Any]:
        """
        Request storage mutation validation from Rust authority.

        If no transport is configured or response is malformed, fail closed.
        """
        request = build_storage_validate(
            correlation_id=correlation_id,
            operation=operation,
            lifecycle_state=lifecycle_state,
            energy_mode=energy_mode,
            execution_type=execution_type,
            encryption_metadata_present=encryption_metadata_present,
            encryption_key_id=encryption_key_id,
        )
        transport = self.storage_transport or self.auth_transport
        if transport is None:
            return build_storage_result(
                correlation_id=correlation_id,
                allowed=False,
                reason="STORAGE_AUTH_UNAVAILABLE",
                retention_applied=False,
                encryption_verified=False,
            )
        response = transport(request)
        if not _is_object(response):
            return build_storage_result(
                correlation_id=correlation_id,
                allowed=False,
                reason="STORAGE_INVALID_RESPONSE",
                retention_applied=False,
                encryption_verified=False,
            )
        parsed = parse_storage_result(response, expected_correlation_id=correlation_id)
        if parsed is None:
            return build_storage_result(
                correlation_id=correlation_id,
                allowed=False,
                reason="STORAGE_INVALID_RESPONSE",
                retention_applied=False,
                encryption_verified=False,
            )
        allowed, reason, retention_applied, encryption_verified = parsed
        return build_storage_result(
            correlation_id=correlation_id,
            allowed=allowed,
            reason=reason,
            retention_applied=retention_applied,
            encryption_verified=encryption_verified,
        )

    def validate_storage_and_maybe_execute(
        self,
        *,
        operation: str,
        lifecycle_state: str,
        energy_mode: str,
        execution_type: str,
        encryption_metadata_present: bool,
        encryption_key_id: str | None,
        correlation_id: str,
        execute_callable: Callable[[], Any],
    ) -> tuple[bool, Any | None, str | None]:
        """
        Validate storage policy via Rust before executing local disk mutation.
        """
        result = self.request_storage_validation(
            operation=operation,
            lifecycle_state=lifecycle_state,
            energy_mode=energy_mode,
            execution_type=execution_type,
            encryption_metadata_present=encryption_metadata_present,
            encryption_key_id=encryption_key_id,
            correlation_id=correlation_id,
        )
        parsed = parse_storage_result(result, expected_correlation_id=correlation_id)
        if parsed is None:
            return (False, None, "STORAGE_INVALID_RESPONSE")
        allowed, reason, _, _ = parsed
        if not allowed:
            return (False, None, reason or "STORAGE_DENIED")
        return (True, execute_callable(), None)

    def request_memory_validation(
        self,
        *,
        current_lifecycle_state: str,
        operation: str,
        energy_mode: str,
        storage_permission_flag: bool,
        metadata_flags: dict[str, bool] | None,
        correlation_id: str,
    ) -> dict[str, Any]:
        """
        Request memory transition validation from Rust authority.

        If no transport is configured or response is malformed, fail closed.
        """
        request = build_memory_validate(
            correlation_id=correlation_id,
            current_lifecycle_state=current_lifecycle_state,
            operation=operation,
            energy_mode=energy_mode,
            storage_permission_flag=storage_permission_flag,
            metadata_flags=metadata_flags,
        )
        transport = self.memory_transport or self.auth_transport
        if transport is None:
            return build_memory_result(
                correlation_id=correlation_id,
                allowed=False,
                reason="MEMORY_AUTH_UNAVAILABLE",
                target_state=None,
                retention_applied=False,
                tier_changed=False,
            )
        response = transport(request)
        if not _is_object(response):
            return build_memory_result(
                correlation_id=correlation_id,
                allowed=False,
                reason="MEMORY_INVALID_RESPONSE",
                target_state=None,
                retention_applied=False,
                tier_changed=False,
            )
        parsed = parse_memory_result(response, expected_correlation_id=correlation_id)
        if parsed is None:
            return build_memory_result(
                correlation_id=correlation_id,
                allowed=False,
                reason="MEMORY_INVALID_RESPONSE",
                target_state=None,
                retention_applied=False,
                tier_changed=False,
            )
        allowed, reason, target_state, retention_applied, tier_changed = parsed
        return build_memory_result(
            correlation_id=correlation_id,
            allowed=allowed,
            reason=reason,
            target_state=target_state,
            retention_applied=retention_applied,
            tier_changed=tier_changed,
        )

    def validate_memory_and_maybe_transition(
        self,
        *,
        current_lifecycle_state: str,
        operation: str,
        energy_mode: str,
        storage_permission_flag: bool,
        metadata_flags: dict[str, bool] | None,
        correlation_id: str,
        transition_callable: Callable[[], Any],
    ) -> tuple[bool, Any | None, str | None]:
        """
        Validate memory transition policy via Rust before state mutation.
        """
        result = self.request_memory_validation(
            current_lifecycle_state=current_lifecycle_state,
            operation=operation,
            energy_mode=energy_mode,
            storage_permission_flag=storage_permission_flag,
            metadata_flags=metadata_flags,
            correlation_id=correlation_id,
        )
        parsed = parse_memory_result(result, expected_correlation_id=correlation_id)
        if parsed is None:
            return (False, None, "MEMORY_INVALID_RESPONSE")
        allowed, reason, _, _, _ = parsed
        if not allowed:
            return (False, None, reason or "MEMORY_DENIED")
        return (True, transition_callable(), None)

    def send_message(self, message: dict[str, Any]) -> None:
        """Write one JSON message to output stream."""
        encoded = json.dumps(message, separators=(",", ":"))
        self.out_stream.write(encoded)
        self.out_stream.write("\n")
        self.out_stream.flush()

    def run_forever(self) -> None:
        """Process stdin lines until EOF."""
        for line in self.in_stream:
            outgoing = self.process_line(line)
            if outgoing is not None:
                self.send_message(outgoing)


def main() -> int:
    bridge = RustBridge(in_stream=sys.stdin, out_stream=sys.stdout, event_handler=None)
    bridge.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
