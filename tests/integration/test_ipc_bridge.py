from __future__ import annotations

import ast
import io
import json
from pathlib import Path
import time

from core.behavior.acceptance_tracker import AcceptanceMetrics
from core.behavior.calibration_engine import CalibrationEngine
from core.cognition.proactive_controller import ProactiveController
from services.ipc.rust_bridge import (
    MESSAGE_AUTH_REQUEST,
    MESSAGE_AUTH_RESULT,
    MESSAGE_ENERGY_RESULT,
    MESSAGE_ENERGY_VALIDATE,
    MESSAGE_EVENT,
    MESSAGE_MEMORY_RESULT,
    MESSAGE_MEMORY_VALIDATE,
    MESSAGE_STORAGE_RESULT,
    MESSAGE_STORAGE_VALIDATE,
    MESSAGE_STATE_UPDATE,
    MESSAGE_TRANSITION_RESULT,
    MESSAGE_TRANSITION_VALIDATE,
    RustBridge,
    build_auth_request,
    build_auth_result,
    build_energy_result,
    build_energy_validate,
    build_memory_result,
    build_memory_validate,
    build_storage_result,
    build_storage_validate,
    build_transition_result,
    build_transition_validate,
    build_state_update,
    parse_auth_result,
    parse_energy_result,
    parse_memory_result,
    parse_storage_result,
    parse_transition_result,
    parse_envelope,
)


def _make_event_line(*, correlation_id: str = "corr-1", event: str = "BatteryLow") -> str:
    envelope = {
        "message_type": MESSAGE_EVENT,
        "timestamp": 123456789,
        "correlation_id": correlation_id,
        "payload": {"event": event, "percent": 15},
    }
    return json.dumps(envelope)


def test_rust_event_received() -> None:
    seen: list[str] = []

    def handler(payload: dict[str, object]) -> None:
        seen.append(str(payload.get("event", "")))

    bridge = RustBridge(in_stream=io.StringIO(""), out_stream=io.StringIO(), event_handler=handler)
    response = bridge.process_line(_make_event_line(correlation_id="corr-evt"))
    assert response is not None
    assert seen == ["BatteryLow"]


def test_invalid_json_handled() -> None:
    bridge = RustBridge(in_stream=io.StringIO(""), out_stream=io.StringIO(), event_handler=None)
    assert parse_envelope("{invalid") is None
    assert bridge.process_line("{invalid") is None


def test_state_update_emission() -> None:
    bridge = RustBridge(in_stream=io.StringIO(""), out_stream=io.StringIO(), event_handler=None)
    response = bridge.process_line(_make_event_line(correlation_id="corr-state"))
    assert response is not None
    assert response["message_type"] == MESSAGE_STATE_UPDATE
    assert response["correlation_id"] == "corr-state"
    assert response["payload"]["component"] == "RustBridge"


def test_no_infinite_loop() -> None:
    bridge = RustBridge(in_stream=io.StringIO(""), out_stream=io.StringIO(), event_handler=None)
    first = bridge.process_line(_make_event_line(correlation_id="corr-loop"))
    assert first is not None
    encoded = json.dumps(first)
    second = bridge.process_line(encoded)
    assert second is None


def test_no_router_import_in_ipc_layer() -> None:
    root = Path(__file__).resolve().parents[2]
    file_path = root / "services" / "ipc" / "rust_bridge.py"
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))

    forbidden = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "router" in alias.name or alias.name in {
                    "core.memory.lifecycle_manager",
                    "core.memory.task_store",
                }:
                    forbidden.append(f"{file_path}:{node.lineno}:{alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if "router" in module or module in {
                "core.memory.lifecycle_manager",
                "core.memory.task_store",
            }:
                forbidden.append(f"{file_path}:{node.lineno}:{module}")

    assert not forbidden, "Forbidden IPC imports:\n" + "\n".join(forbidden)


def test_no_mutation_call_in_ipc_layer() -> None:
    root = Path(__file__).resolve().parents[2]
    file_path = root / "services" / "ipc" / "rust_bridge.py"
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    forbidden_calls = {"create_task", "complete_task", "archive_task", "transition_task", "route"}

    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        called = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
        if called in forbidden_calls:
            violations.append(f"{file_path}:{node.lineno}:{called}")

    assert not violations, "Forbidden IPC mutation calls:\n" + "\n".join(violations)


def test_calibration_unaffected() -> None:
    engine = CalibrationEngine(config_path="configs/default.yaml")
    metrics = AcceptanceMetrics(
        accepted=8,
        rejected=1,
        ignored=1,
        overrides=0,
        acceptance_rate=0.8,
    )
    updated = engine.update_threshold(0.7, metrics)
    assert updated < 0.7


def test_proactive_unaffected() -> None:
    controller = ProactiveController(confidence_threshold=0.7, daily_limit=3)
    suggestions = controller.evaluate(
        {
            "overdue_tasks": 2,
            "scheduled_tasks_today": 5,
            "daily_capacity": 8,
            "goal_alignment_score": 0.9,
        }
    )
    assert len(suggestions) >= 1


def test_build_state_update_uses_correlation_id() -> None:
    envelope = build_state_update(
        correlation_id="corr-test",
        component="Governor",
        details={"mode": "LOW_POWER"},
    )
    assert envelope["correlation_id"] == "corr-test"
    assert envelope["message_type"] == MESSAGE_STATE_UPDATE


def test_auth_request_sent_before_router() -> None:
    call_order: list[str] = []
    sent_messages: list[dict[str, object]] = []

    def fake_auth_transport(request: dict[str, object]) -> dict[str, object]:
        call_order.append("auth")
        sent_messages.append(request)
        return build_auth_result(correlation_id=str(request["correlation_id"]), allowed=True, reason=None)

    def fake_route() -> str:
        call_order.append("route")
        return "ROUTED"

    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        auth_transport=fake_auth_transport,
    )
    allowed, result, reason = bridge.authorize_and_maybe_route(
        user_id="owner",
        tier="Owner",
        action="CREATE_TASK",
        authenticated=True,
        correlation_id="auth-1",
        route_callable=fake_route,
    )

    assert allowed is True
    assert result == "ROUTED"
    assert reason is None
    assert call_order == ["auth", "route"]
    assert sent_messages[0]["message_type"] == MESSAGE_AUTH_REQUEST


def test_denied_action_not_routed() -> None:
    routed = {"count": 0}

    def fake_auth_transport(request: dict[str, object]) -> dict[str, object]:
        return build_auth_result(
            correlation_id=str(request["correlation_id"]),
            allowed=False,
            reason="ACCESS_DENIED",
        )

    def fake_route() -> str:
        routed["count"] += 1
        return "ROUTED"

    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        auth_transport=fake_auth_transport,
    )
    allowed, result, reason = bridge.authorize_and_maybe_route(
        user_id="guest",
        tier="Guest",
        action="CREATE_TASK",
        authenticated=True,
        correlation_id="auth-2",
        route_callable=fake_route,
    )

    assert allowed is False
    assert result is None
    assert reason == "ACCESS_DENIED"
    assert routed["count"] == 0


def test_allowed_action_routed() -> None:
    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        auth_transport=lambda request: build_auth_result(
            correlation_id=str(request["correlation_id"]),
            allowed=True,
            reason=None,
        ),
    )
    allowed, result, reason = bridge.authorize_and_maybe_route(
        user_id="owner",
        tier="Owner",
        action="COMPLETE_TASK",
        authenticated=True,
        correlation_id="auth-3",
        route_callable=lambda: "OK",
    )
    assert allowed is True
    assert result == "OK"
    assert reason is None


def test_no_router_call_when_denied() -> None:
    invoked = {"called": False}

    def fake_route() -> str:
        invoked["called"] = True
        return "SHOULD_NOT_ROUTE"

    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        auth_transport=lambda request: build_auth_result(
            correlation_id=str(request["correlation_id"]),
            allowed=False,
            reason="UNAUTHENTICATED",
        ),
    )
    allowed, _, reason = bridge.authorize_and_maybe_route(
        user_id="owner",
        tier="Owner",
        action="CREATE_TASK",
        authenticated=False,
        correlation_id="auth-4",
        route_callable=fake_route,
    )
    assert allowed is False
    assert invoked["called"] is False
    assert reason == "UNAUTHENTICATED"


def test_no_identity_bypass() -> None:
    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        auth_transport=None,
    )
    allowed, result, reason = bridge.authorize_and_maybe_route(
        user_id="owner",
        tier="Owner",
        action="CREATE_TASK",
        authenticated=True,
        correlation_id="auth-5",
        route_callable=lambda: "ROUTED",
    )
    assert allowed is False
    assert result is None
    assert reason == "AUTH_UNAVAILABLE"


def test_auth_result_parser_and_correlation() -> None:
    envelope = build_auth_result(correlation_id="corr-auth", allowed=True, reason=None)
    parsed = parse_auth_result(envelope, expected_correlation_id="corr-auth")
    assert parsed == (True, None)

    wrong = parse_auth_result(envelope, expected_correlation_id="different")
    assert wrong is None


def test_build_auth_request_schema() -> None:
    request = build_auth_request(
        correlation_id="corr-req",
        user_id="owner",
        tier="Owner",
        action="CREATE_TASK",
        authenticated=True,
    )
    assert request["message_type"] == MESSAGE_AUTH_REQUEST
    assert request["correlation_id"] == "corr-req"
    assert request["payload"]["user_id"] == "owner"
    assert request["payload"]["tier"] == "Owner"


def test_parse_envelope_supports_auth_result() -> None:
    raw = json.dumps(
        {
            "message_type": MESSAGE_AUTH_RESULT,
            "timestamp": 1,
            "correlation_id": "corr-res",
            "payload": {"allowed": True, "reason": None},
        }
    )
    parsed = parse_envelope(raw)
    assert parsed is not None
    assert parsed["message_type"] == MESSAGE_AUTH_RESULT


def test_transition_validation_sent_before_mutation() -> None:
    call_order: list[str] = []
    sent: list[dict[str, object]] = []

    def fake_transition_transport(request: dict[str, object]) -> dict[str, object]:
        call_order.append("transition")
        sent.append(request)
        return build_transition_result(
            correlation_id=str(request["correlation_id"]),
            allowed=True,
            reason=None,
        )

    def fake_route() -> str:
        call_order.append("route")
        return "ROUTED"

    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        transition_transport=fake_transition_transport,
    )
    allowed, result, reason = bridge.validate_transition_and_maybe_route(
        current_state="Pending",
        requested_state="Completed",
        correlation_id="tr-1",
        route_callable=fake_route,
    )
    assert allowed is True
    assert result == "ROUTED"
    assert reason is None
    assert call_order == ["transition", "route"]
    assert sent[0]["message_type"] == MESSAGE_TRANSITION_VALIDATE


def test_invalid_transition_not_routed() -> None:
    routed = {"count": 0}

    def fake_transition_transport(request: dict[str, object]) -> dict[str, object]:
        return build_transition_result(
            correlation_id=str(request["correlation_id"]),
            allowed=False,
            reason="INVALID_TRANSITION",
        )

    def fake_route() -> str:
        routed["count"] += 1
        return "ROUTED"

    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        transition_transport=fake_transition_transport,
    )
    allowed, result, reason = bridge.validate_transition_and_maybe_route(
        current_state="Completed",
        requested_state="Pending",
        correlation_id="tr-2",
        route_callable=fake_route,
    )
    assert allowed is False
    assert result is None
    assert reason == "INVALID_TRANSITION"
    assert routed["count"] == 0


def test_valid_transition_routed() -> None:
    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        transition_transport=lambda request: build_transition_result(
            correlation_id=str(request["correlation_id"]),
            allowed=True,
            reason=None,
        ),
    )
    allowed, result, reason = bridge.validate_transition_and_maybe_route(
        current_state="Pending",
        requested_state="Archived",
        correlation_id="tr-3",
        route_callable=lambda: "OK",
    )
    assert allowed is True
    assert result == "OK"
    assert reason is None


def test_no_local_lifecycle_validation() -> None:
    root = Path(__file__).resolve().parents[2]
    file_path = root / "services" / "ipc" / "rust_bridge.py"
    source = file_path.read_text(encoding="utf-8")
    # Bridge should not embed a local transition matrix.
    assert "ALLOWED_TRANSITIONS" not in source
    assert "Legacy" not in source


def test_no_router_call_when_transition_denied() -> None:
    invoked = {"called": False}

    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        transition_transport=lambda request: build_transition_result(
            correlation_id=str(request["correlation_id"]),
            allowed=False,
            reason="ARCHIVED_TERMINAL",
        ),
    )

    def fake_route() -> str:
        invoked["called"] = True
        return "SHOULD_NOT_ROUTE"

    allowed, _, reason = bridge.validate_transition_and_maybe_route(
        current_state="Archived",
        requested_state="Completed",
        correlation_id="tr-4",
        route_callable=fake_route,
    )
    assert allowed is False
    assert invoked["called"] is False
    assert reason == "ARCHIVED_TERMINAL"


def test_transition_result_correlation_preserved() -> None:
    request = build_transition_validate(
        correlation_id="tr-corr",
        current_state="Pending",
        requested_state="Completed",
    )
    assert request["message_type"] == MESSAGE_TRANSITION_VALIDATE

    result = build_transition_result(
        correlation_id="tr-corr",
        allowed=True,
        reason=None,
    )
    parsed = parse_transition_result(result, expected_correlation_id="tr-corr")
    assert parsed == (True, None)


def test_parse_envelope_supports_transition_result() -> None:
    raw = json.dumps(
        {
            "message_type": MESSAGE_TRANSITION_RESULT,
            "timestamp": 1,
            "correlation_id": "corr-transition",
            "payload": {"allowed": False, "reason": "INVALID_TRANSITION"},
        }
    )
    parsed = parse_envelope(raw)
    assert parsed is not None
    assert parsed["message_type"] == MESSAGE_TRANSITION_RESULT


def test_energy_validate_sent_before_llm() -> None:
    call_order: list[str] = []
    sent: list[dict[str, object]] = []

    def fake_energy_transport(request: dict[str, object]) -> dict[str, object]:
        call_order.append("energy")
        sent.append(request)
        return build_energy_result(
            correlation_id=str(request["correlation_id"]),
            allowed=True,
            reason=None,
        )

    def fake_llm() -> str:
        call_order.append("llm")
        return "LLM_OK"

    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        energy_transport=fake_energy_transport,
    )
    allowed, result, reason = bridge.validate_energy_and_maybe_execute(
        battery_percent=70,
        execution_type="LLM",
        correlation_id="energy-1",
        execute_callable=fake_llm,
    )

    assert allowed is True
    assert result == "LLM_OK"
    assert reason is None
    assert call_order == ["energy", "llm"]
    assert sent[0]["message_type"] == MESSAGE_ENERGY_VALIDATE


def test_energy_denied_skips_llm() -> None:
    invoked = {"count": 0}

    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        energy_transport=lambda request: build_energy_result(
            correlation_id=str(request["correlation_id"]),
            allowed=False,
            reason="LLM_BLOCKED_SILENT",
        ),
    )

    def fake_llm() -> str:
        invoked["count"] += 1
        return "SHOULD_NOT_RUN"

    allowed, result, reason = bridge.validate_energy_and_maybe_execute(
        battery_percent=10,
        execution_type="LLM",
        correlation_id="energy-2",
        execute_callable=fake_llm,
    )
    assert allowed is False
    assert result is None
    assert reason == "LLM_BLOCKED_SILENT"
    assert invoked["count"] == 0


def test_energy_allowed_executes_llm() -> None:
    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        energy_transport=lambda request: build_energy_result(
            correlation_id=str(request["correlation_id"]),
            allowed=True,
            reason=None,
        ),
    )
    allowed, result, reason = bridge.validate_energy_and_maybe_execute(
        battery_percent=85,
        execution_type="LLM",
        correlation_id="energy-3",
        execute_callable=lambda: "EXECUTED",
    )
    assert allowed is True
    assert result == "EXECUTED"
    assert reason is None


def test_no_execution_without_validation() -> None:
    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        energy_transport=None,
    )
    allowed, result, reason = bridge.validate_energy_and_maybe_execute(
        battery_percent=60,
        execution_type="PROACTIVE",
        correlation_id="energy-4",
        execute_callable=lambda: "SHOULD_NOT_EXECUTE",
    )
    assert allowed is False
    assert result is None
    assert reason == "ENERGY_AUTH_UNAVAILABLE"


def test_fail_closed_on_ipc_failure() -> None:
    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        energy_transport=lambda _request: None,
    )
    allowed, result, reason = bridge.validate_energy_and_maybe_execute(
        battery_percent=40,
        execution_type="BACKGROUND_TASK",
        correlation_id="energy-5",
        execute_callable=lambda: "SHOULD_NOT_EXECUTE",
    )
    assert allowed is False
    assert result is None
    assert reason == "ENERGY_INVALID_RESPONSE"


def test_no_energy_bypass() -> None:
    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        energy_transport=lambda request: build_energy_result(
            correlation_id=str(request["correlation_id"]),
            allowed=False,
            reason="BACKGROUND_BLOCKED_REDUCED",
        ),
    )
    allowed, result, reason = bridge.validate_energy_and_maybe_execute(
        battery_percent=30,
        execution_type="BACKGROUND_TASK",
        correlation_id="energy-6",
        execute_callable=lambda: "NO",
    )
    assert allowed is False
    assert result is None
    assert reason == "BACKGROUND_BLOCKED_REDUCED"


def test_energy_correlation_preserved() -> None:
    request = build_energy_validate(
        correlation_id="energy-corr",
        battery_percent=55,
        execution_type="LLM",
    )
    assert request["message_type"] == MESSAGE_ENERGY_VALIDATE

    result = build_energy_result(
        correlation_id="energy-corr",
        allowed=True,
        reason=None,
    )
    parsed = parse_energy_result(result, expected_correlation_id="energy-corr")
    assert parsed == (True, None)


def test_parse_envelope_supports_energy_result() -> None:
    raw = json.dumps(
        {
            "message_type": MESSAGE_ENERGY_RESULT,
            "timestamp": 1,
            "correlation_id": "corr-energy",
            "payload": {"allowed": False, "reason": "LLM_BLOCKED_SILENT"},
        }
    )
    parsed = parse_envelope(raw)
    assert parsed is not None
    assert parsed["message_type"] == MESSAGE_ENERGY_RESULT


def test_storage_validation_sent_before_write() -> None:
    call_order: list[str] = []
    sent: list[dict[str, object]] = []

    def fake_storage_transport(request: dict[str, object]) -> dict[str, object]:
        call_order.append("storage")
        sent.append(request)
        return build_storage_result(
            correlation_id=str(request["correlation_id"]),
            allowed=True,
            reason=None,
            retention_applied=False,
            encryption_verified=True,
        )

    def fake_write() -> str:
        call_order.append("write")
        return "WRITE_OK"

    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        storage_transport=fake_storage_transport,
    )
    allowed, result, reason = bridge.validate_storage_and_maybe_execute(
        operation="WRITE_TASK",
        lifecycle_state="CREATED",
        energy_mode="STRATEGIC",
        execution_type="BACKGROUND_TASK",
        encryption_metadata_present=True,
        encryption_key_id="key-1",
        correlation_id="storage-1",
        execute_callable=fake_write,
    )

    assert allowed is True
    assert result == "WRITE_OK"
    assert reason is None
    assert call_order == ["storage", "write"]
    assert sent[0]["message_type"] == MESSAGE_STORAGE_VALIDATE


def test_storage_denied_skips_disk_io() -> None:
    writes = {"count": 0}

    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        storage_transport=lambda request: build_storage_result(
            correlation_id=str(request["correlation_id"]),
            allowed=False,
            reason="RETENTION_DELETE_DENIED",
            retention_applied=True,
            encryption_verified=True,
        ),
    )

    def fake_write() -> str:
        writes["count"] += 1
        return "SHOULD_NOT_WRITE"

    allowed, result, reason = bridge.validate_storage_and_maybe_execute(
        operation="DELETE_TASK",
        lifecycle_state="COMPLETED",
        energy_mode="STRATEGIC",
        execution_type="BACKGROUND_TASK",
        encryption_metadata_present=True,
        encryption_key_id="key-1",
        correlation_id="storage-2",
        execute_callable=fake_write,
    )

    assert allowed is False
    assert result is None
    assert reason == "RETENTION_DELETE_DENIED"
    assert writes["count"] == 0


def test_storage_allowed_executes_io() -> None:
    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        storage_transport=lambda request: build_storage_result(
            correlation_id=str(request["correlation_id"]),
            allowed=True,
            reason=None,
            retention_applied=False,
            encryption_verified=True,
        ),
    )
    allowed, result, reason = bridge.validate_storage_and_maybe_execute(
        operation="UPDATE_TASK",
        lifecycle_state="ACTIVE",
        energy_mode="STRATEGIC",
        execution_type="BACKGROUND_TASK",
        encryption_metadata_present=True,
        encryption_key_id="key-2",
        correlation_id="storage-3",
        execute_callable=lambda: "UPDATED",
    )
    assert allowed is True
    assert result == "UPDATED"
    assert reason is None


def test_storage_fail_closed_when_ipc_fails() -> None:
    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        storage_transport=lambda _request: None,
    )
    allowed, result, reason = bridge.validate_storage_and_maybe_execute(
        operation="WRITE_TASK",
        lifecycle_state="CREATED",
        energy_mode="STRATEGIC",
        execution_type="BACKGROUND_TASK",
        encryption_metadata_present=True,
        encryption_key_id="key-3",
        correlation_id="storage-4",
        execute_callable=lambda: "SHOULD_NOT_WRITE",
    )
    assert allowed is False
    assert result is None
    assert reason == "STORAGE_INVALID_RESPONSE"


def test_storage_correlation_preserved() -> None:
    request = build_storage_validate(
        correlation_id="storage-corr",
        operation="WRITE_TASK",
        lifecycle_state="CREATED",
        energy_mode="STRATEGIC",
        execution_type="BACKGROUND_TASK",
        encryption_metadata_present=True,
        encryption_key_id="key-4",
    )
    assert request["message_type"] == MESSAGE_STORAGE_VALIDATE
    result = build_storage_result(
        correlation_id="storage-corr",
        allowed=True,
        reason=None,
        retention_applied=False,
        encryption_verified=True,
    )
    parsed = parse_storage_result(result, expected_correlation_id="storage-corr")
    assert parsed == (True, None, False, True)


def test_parse_envelope_supports_storage_result() -> None:
    raw = json.dumps(
        {
            "message_type": MESSAGE_STORAGE_RESULT,
            "timestamp": 1,
            "correlation_id": "corr-storage",
            "payload": {
                "allowed": True,
                "reason": None,
                "retention_applied": False,
                "encryption_verified": True,
            },
        }
    )
    parsed = parse_envelope(raw)
    assert parsed is not None
    assert parsed["message_type"] == MESSAGE_STORAGE_RESULT


def test_storage_validation_latency_under_2ms_average() -> None:
    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        storage_transport=lambda request: build_storage_result(
            correlation_id=str(request["correlation_id"]),
            allowed=True,
            reason=None,
            retention_applied=False,
            encryption_verified=True,
        ),
    )
    iterations = 2000
    start = time.perf_counter()
    for index in range(iterations):
        bridge.request_storage_validation(
            operation="WRITE_TASK",
            lifecycle_state="CREATED",
            energy_mode="STRATEGIC",
            execution_type="BACKGROUND_TASK",
            encryption_metadata_present=True,
            encryption_key_id="key-latency",
            correlation_id=f"storage-latency-{index}",
        )
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    average_ms = elapsed_ms / iterations
    assert average_ms < 2.0


def test_memory_validation_occurs_before_transition() -> None:
    call_order: list[str] = []
    sent: list[dict[str, object]] = []

    def fake_memory_transport(request: dict[str, object]) -> dict[str, object]:
        call_order.append("memory")
        sent.append(request)
        return build_memory_result(
            correlation_id=str(request["correlation_id"]),
            allowed=True,
            reason=None,
            target_state="ARCHIVED",
            retention_applied=True,
            tier_changed=True,
        )

    def fake_transition() -> str:
        call_order.append("transition")
        return "TRANSITIONED"

    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        memory_transport=fake_memory_transport,
    )
    allowed, result, reason = bridge.validate_memory_and_maybe_transition(
        current_lifecycle_state="ACTIVE",
        operation="ARCHIVE_ITEM",
        energy_mode="STRATEGIC",
        storage_permission_flag=True,
        metadata_flags={"retention_due": True},
        correlation_id="memory-1",
        transition_callable=fake_transition,
    )

    assert allowed is True
    assert result == "TRANSITIONED"
    assert reason is None
    assert call_order == ["memory", "transition"]
    assert sent[0]["message_type"] == MESSAGE_MEMORY_VALIDATE


def test_memory_denied_skips_mutation() -> None:
    mutated = {"count": 0}

    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        memory_transport=lambda request: build_memory_result(
            correlation_id=str(request["correlation_id"]),
            allowed=False,
            reason="SILENT_MODE_MEMORY_RESTRICTED",
            target_state=None,
            retention_applied=False,
            tier_changed=False,
        ),
    )

    def fake_transition() -> str:
        mutated["count"] += 1
        return "SHOULD_NOT_MUTATE"

    allowed, result, reason = bridge.validate_memory_and_maybe_transition(
        current_lifecycle_state="ACTIVE",
        operation="DEMOTE_TO_DORMANT",
        energy_mode="SILENT",
        storage_permission_flag=True,
        metadata_flags={"critical_reminder": False},
        correlation_id="memory-2",
        transition_callable=fake_transition,
    )

    assert allowed is False
    assert result is None
    assert reason == "SILENT_MODE_MEMORY_RESTRICTED"
    assert mutated["count"] == 0


def test_memory_allowed_performs_mutation() -> None:
    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        memory_transport=lambda request: build_memory_result(
            correlation_id=str(request["correlation_id"]),
            allowed=True,
            reason=None,
            target_state="COMPLETED",
            retention_applied=False,
            tier_changed=True,
        ),
    )
    allowed, result, reason = bridge.validate_memory_and_maybe_transition(
        current_lifecycle_state="ACTIVE",
        operation="DEMOTE_TO_DORMANT",
        energy_mode="STRATEGIC",
        storage_permission_flag=True,
        metadata_flags={},
        correlation_id="memory-3",
        transition_callable=lambda: "MUTATED",
    )
    assert allowed is True
    assert result == "MUTATED"
    assert reason is None


def test_memory_fail_closed_when_ipc_fails() -> None:
    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        memory_transport=lambda _request: None,
    )
    allowed, result, reason = bridge.validate_memory_and_maybe_transition(
        current_lifecycle_state="ACTIVE",
        operation="ARCHIVE_ITEM",
        energy_mode="STRATEGIC",
        storage_permission_flag=True,
        metadata_flags={"retention_due": True},
        correlation_id="memory-4",
        transition_callable=lambda: "SHOULD_NOT_MUTATE",
    )
    assert allowed is False
    assert result is None
    assert reason == "MEMORY_INVALID_RESPONSE"


def test_memory_correlation_preserved() -> None:
    request = build_memory_validate(
        correlation_id="memory-corr",
        current_lifecycle_state="ACTIVE",
        operation="ARCHIVE_ITEM",
        energy_mode="STRATEGIC",
        storage_permission_flag=True,
        metadata_flags={"retention_due": True},
    )
    assert request["message_type"] == MESSAGE_MEMORY_VALIDATE
    result = build_memory_result(
        correlation_id="memory-corr",
        allowed=True,
        reason=None,
        target_state="ARCHIVED",
        retention_applied=True,
        tier_changed=True,
    )
    parsed = parse_memory_result(result, expected_correlation_id="memory-corr")
    assert parsed == (True, None, "ARCHIVED", True, True)


def test_parse_envelope_supports_memory_result() -> None:
    raw = json.dumps(
        {
            "message_type": MESSAGE_MEMORY_RESULT,
            "timestamp": 1,
            "correlation_id": "corr-memory",
            "payload": {
                "allowed": False,
                "reason": "STORAGE_PERMISSION_REQUIRED",
                "target_state": None,
                "retention_applied": False,
                "tier_changed": False,
            },
        }
    )
    parsed = parse_envelope(raw)
    assert parsed is not None
    assert parsed["message_type"] == MESSAGE_MEMORY_RESULT


def test_memory_validation_no_bypass_path() -> None:
    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        memory_transport=None,
    )
    allowed, result, reason = bridge.validate_memory_and_maybe_transition(
        current_lifecycle_state="ACTIVE",
        operation="ARCHIVE_ITEM",
        energy_mode="STRATEGIC",
        storage_permission_flag=True,
        metadata_flags={"retention_due": True},
        correlation_id="memory-5",
        transition_callable=lambda: "NO",
    )
    assert allowed is False
    assert result is None
    assert reason == "MEMORY_AUTH_UNAVAILABLE"


def test_memory_validation_latency_under_2ms_average() -> None:
    bridge = RustBridge(
        in_stream=io.StringIO(""),
        out_stream=io.StringIO(),
        memory_transport=lambda request: build_memory_result(
            correlation_id=str(request["correlation_id"]),
            allowed=True,
            reason=None,
            target_state="ACTIVE",
            retention_applied=False,
            tier_changed=True,
        ),
    )
    iterations = 2000
    start = time.perf_counter()
    for index in range(iterations):
        bridge.request_memory_validation(
            current_lifecycle_state="ACTIVE",
            operation="PROMOTE_TO_ACTIVE",
            energy_mode="STRATEGIC",
            storage_permission_flag=True,
            metadata_flags={},
            correlation_id=f"memory-latency-{index}",
        )
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    average_ms = elapsed_ms / iterations
    assert average_ms < 2.0
