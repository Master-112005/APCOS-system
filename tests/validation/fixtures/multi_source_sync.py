"""Validation fixtures for multi-source sync behavioral tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.connectors.mobile_connector import MobileConnector
from services.sync_daemon import SyncDaemon


class CaptureBridge:
    """In-memory envelope sink used by connector/daemon mocks."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def publish_event(self, message: dict[str, Any]) -> None:
        self.messages.append(dict(message))

    def send_message(self, message: dict[str, Any]) -> None:
        self.messages.append(dict(message))


class MockMobileConnector:
    """Envelope-only mobile event producer for behavioral validation."""

    def __init__(self, *, source: str = "mobile") -> None:
        self.bridge = CaptureBridge()
        self._connector = MobileConnector(self.bridge, source=source)

    def emit(
        self,
        *,
        action: str,
        payload: dict[str, Any],
        correlation_id: str,
    ) -> dict[str, Any]:
        return self._connector.receive_event(
            {
                "action": action,
                "payload": payload,
                "correlation_id": correlation_id,
            }
        )


class MockSyncDaemon:
    """Envelope-only sync producer for behavioral validation."""

    def __init__(self, *, source: str = "sync-daemon") -> None:
        self.bridge = CaptureBridge()
        self._daemon = SyncDaemon(self.bridge, source=source)

    def emit(
        self,
        *,
        source_id: str,
        sync_type: str,
        payload: dict[str, Any],
        correlation_id: str,
        merge_hint: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._daemon.receive_sync(
            {
                "source_id": source_id,
                "sync_type": sync_type,
                "payload": payload,
                "correlation_id": correlation_id,
                "merge_hint": merge_hint or {},
            }
        )


@dataclass(frozen=True)
class MockEnergyState:
    """Simple deterministic energy context used for proactive evaluation."""

    mode: str
    battery_percent: int


@dataclass(frozen=True)
class MockIdentityContext:
    """Simple deterministic identity context for scenario metadata."""

    user_id: str
    tier: str
    authenticated: bool

