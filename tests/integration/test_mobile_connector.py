from __future__ import annotations

import ast
from pathlib import Path
import time

import pytest

from core.connectors.mobile_connector import MobileConnector


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


def test_valid_event_forwarded_to_ipc() -> None:
    bridge = CaptureBridge()
    connector = MobileConnector(bridge)

    message = connector.receive_event(
        {
            "action": "create_task",
            "payload": {"task": "Review weekly plan"},
            "correlation_id": "mobile-corr-1",
        }
    )

    assert len(bridge.messages) == 1
    assert message["message_type"] == "EVENT"
    assert message["correlation_id"] == "mobile-corr-1"
    assert message["payload"]["event"] == "TaskCreated"
    assert message["payload"]["data"]["source"] == "mobile"


def test_malformed_payload_rejected() -> None:
    bridge = CaptureBridge()
    connector = MobileConnector(bridge)

    with pytest.raises(ValueError):
        connector.receive_event({"action": "create_task", "payload": "bad"})

    assert bridge.messages == []


def test_authority_denial_stops_action() -> None:
    bridge = AuthorityGateBridge(allow=False)
    connector = MobileConnector(bridge)

    connector.receive_event(
        {
            "action": "archive_task",
            "payload": {"task_id": 17},
            "correlation_id": "mobile-corr-2",
        }
    )

    assert len(bridge.messages) == 1
    assert bridge.denied_count == 1
    assert bridge.mutation_count == 0


def test_event_bus_receives_expected_envelope_shape() -> None:
    bridge = CaptureBridge()
    connector = MobileConnector(bridge, source="mobile-app")

    connector.receive_event(
        {
            "action": "complete_task",
            "payload": {"task_id": 88},
            "correlation_id": "mobile-corr-3",
        }
    )

    envelope = bridge.messages[0]
    assert envelope["message_type"] == "EVENT"
    assert envelope["payload"]["event"] == "TaskCompleted"
    assert envelope["payload"]["data"]["source"] == "mobile-app"
    assert envelope["payload"]["data"]["payload"]["task_id"] == 88


def test_correlation_id_preserved_end_to_end() -> None:
    bridge = CaptureBridge()
    connector = MobileConnector(bridge)

    connector.receive_event(
        {
            "action": "reminder_ack",
            "payload": {"reminder_id": "r-1"},
            "correlation_id": "mobile-correlation-42",
        }
    )

    assert bridge.messages[0]["correlation_id"] == "mobile-correlation-42"


def test_no_memory_imports_in_mobile_connector() -> None:
    root = Path(__file__).resolve().parents[2]
    file_path = root / "core" / "connectors" / "mobile_connector.py"
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

    assert not violations, "Forbidden mobile connector imports:\n" + "\n".join(violations)


def test_connector_overhead_under_1ms_average() -> None:
    bridge = CaptureBridge()
    connector = MobileConnector(bridge)
    iterations = 2000
    start = time.perf_counter()
    for index in range(iterations):
        connector.receive_event(
            {
                "action": "create_task",
                "payload": {"task": f"Task {index}"},
                "correlation_id": f"perf-{index}",
            }
        )
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    average_ms = elapsed_ms / iterations
    assert average_ms < 1.0

