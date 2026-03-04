from __future__ import annotations

import ast
from pathlib import Path
import time

import pytest

from services.sync_daemon import SyncDaemon


class CaptureBridge:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    def send_message(self, message: dict[str, object]) -> None:
        self.messages.append(message)


class AuthorityGateBridge:
    def __init__(self, *, allow: bool) -> None:
        self.allow = allow
        self.messages: list[dict[str, object]] = []
        self.mutation_count = 0
        self.denied_count = 0

    def send_message(self, message: dict[str, object]) -> None:
        self.messages.append(message)
        if self.allow:
            self.mutation_count += 1
        else:
            self.denied_count += 1


def _valid_sync_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_id": "mobile-device-1",
        "sync_type": "TASK_UPDATE",
        "payload": {"task_id": "t-1", "status": "pending"},
        "timestamp": 1700000000,
        "correlation_id": "sync-corr-1",
        "merge_hint": {
            "source_priority": "normal",
            "version": "v2",
            "external_timestamp": 1700000001,
        },
    }
    payload.update(overrides)
    return payload


def test_valid_sync_forwarded_to_ipc() -> None:
    bridge = CaptureBridge()
    daemon = SyncDaemon(bridge)

    message = daemon.receive_sync(_valid_sync_payload())

    assert len(bridge.messages) == 1
    assert message["message_type"] == "EVENT"
    assert message["correlation_id"] == "sync-corr-1"
    assert message["payload"]["data"]["source"] == "sync-daemon"
    assert message["payload"]["data"]["sync"]["source_id"] == "mobile-device-1"
    assert message["payload"]["data"]["sync"]["sync_type"] == "TASK_UPDATE"
    assert message["payload"]["data"]["sync"]["payload"]["task_id"] == "t-1"


def test_malformed_payload_rejected() -> None:
    bridge = CaptureBridge()
    daemon = SyncDaemon(bridge)

    with pytest.raises(ValueError):
        daemon.receive_sync({"source_id": "mobile-device-1", "sync_type": "TASK_UPDATE", "payload": "bad"})

    assert bridge.messages == []


def test_merge_hint_preserved() -> None:
    bridge = CaptureBridge()
    daemon = SyncDaemon(bridge)

    daemon.receive_sync(
        _valid_sync_payload(
            merge_hint={
                "source_priority": "high",
                "version": "v9",
                "external_timestamp": 1800000000,
            }
        )
    )

    sync = bridge.messages[0]["payload"]["data"]["sync"]
    merge_hint = sync["merge_hint"]
    assert merge_hint["source_priority"] == "high"
    assert merge_hint["version"] == "v9"
    assert merge_hint["external_timestamp"] == 1800000000


def test_correlation_id_preserved() -> None:
    bridge = CaptureBridge()
    daemon = SyncDaemon(bridge)

    daemon.receive_sync(_valid_sync_payload(correlation_id="sync-correlation-42"))

    assert bridge.messages[0]["correlation_id"] == "sync-correlation-42"


def test_authority_denial_respected_no_mutation_occurs() -> None:
    bridge = AuthorityGateBridge(allow=False)
    daemon = SyncDaemon(bridge)

    daemon.receive_sync(_valid_sync_payload(sync_type="ARCHIVAL_HINT"))

    assert len(bridge.messages) == 1
    assert bridge.denied_count == 1
    assert bridge.mutation_count == 0


def test_multi_source_updates_maintain_envelope_integrity() -> None:
    bridge = CaptureBridge()
    daemon = SyncDaemon(bridge)

    daemon.receive_sync(
        _valid_sync_payload(
            source_id="mobile-device-1",
            sync_type="TASK_SNAPSHOT",
            payload={"task_count": 5},
            correlation_id="sync-a",
        )
    )
    daemon.receive_sync(
        _valid_sync_payload(
            source_id="laptop-client-2",
            sync_type="VECTOR_UPDATE",
            payload={"vector_id": "v-77"},
            correlation_id="sync-b",
        )
    )

    first_sync = bridge.messages[0]["payload"]["data"]["sync"]
    second_sync = bridge.messages[1]["payload"]["data"]["sync"]

    assert first_sync["source_id"] == "mobile-device-1"
    assert first_sync["sync_type"] == "TASK_SNAPSHOT"
    assert first_sync["payload"]["task_count"] == 5
    assert bridge.messages[0]["correlation_id"] == "sync-a"

    assert second_sync["source_id"] == "laptop-client-2"
    assert second_sync["sync_type"] == "VECTOR_UPDATE"
    assert second_sync["payload"]["vector_id"] == "v-77"
    assert bridge.messages[1]["correlation_id"] == "sync-b"


def test_no_memory_imports_in_sync_daemon() -> None:
    root = Path(__file__).resolve().parents[2]
    file_path = root / "services" / "sync_daemon.py"
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))

    forbidden_modules = {
        "core.memory.lifecycle_manager",
        "core.memory.task_store",
        "core.memory.vector_memory",
    }
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden_modules:
                    violations.append(f"{file_path}:{node.lineno}:{alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module in forbidden_modules:
                violations.append(f"{file_path}:{node.lineno}:{module}")

    assert not violations, "Forbidden sync daemon imports:\n" + "\n".join(violations)


def test_sync_daemon_overhead_under_2ms_average() -> None:
    bridge = CaptureBridge()
    daemon = SyncDaemon(bridge)

    iterations = 2000
    start = time.perf_counter()
    for index in range(iterations):
        daemon.receive_sync(
            _valid_sync_payload(
                source_id=f"src-{index % 4}",
                correlation_id=f"sync-perf-{index}",
                payload={"task_id": f"t-{index}", "status": "pending"},
            )
        )
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    average_ms = elapsed_ms / iterations
    assert average_ms < 2.0
