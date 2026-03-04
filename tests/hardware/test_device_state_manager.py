from __future__ import annotations

import ast
from pathlib import Path

from core.behavior.cpu_monitor import CPUMonitor
from core.behavior.memory_monitor import MemoryMonitor
from core.behavior.resource_governor import ResourceGovernor
from services.hardware.battery_monitor import BatteryMonitor
from services.hardware.device_state_manager import (
    DeviceStateManager,
    STATE_CRITICAL,
    STATE_SLEEP,
    STATE_THERMAL_LIMIT,
)
from services.hardware.microphone_health import MicrophoneHealth
from services.hardware.sleep_manager import SleepManager
from services.hardware.thermal_monitor import ThermalMonitor
from voice.model_manager import MODEL_TINY, ModelManager


class _SignalGovernor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def force_model_downgrade(self, *, reason: str = "") -> bool:
        self.calls.append(("force_model_downgrade", reason))
        return True

    def force_model_unload(self, *, reason: str = "") -> bool:
        self.calls.append(("force_model_unload", reason))
        return True

    def reduce_cpu_budget(self, *, reason: str = "", budget_scale: float = 0.5) -> bool:
        _ = budget_scale
        self.calls.append(("reduce_cpu_budget", reason))
        return True

    def pause_evaluation(self, *, reason: str = "") -> bool:
        self.calls.append(("pause_evaluation", reason))
        return True

    def resume_evaluation(self, *, reason: str = "") -> bool:
        self.calls.append(("resume_evaluation", reason))
        return True


def test_battery_low_triggers_governor_signal() -> None:
    governor = _SignalGovernor()
    manager = DeviceStateManager(
        battery_monitor=BatteryMonitor(
            low_percent=20,
            critical_percent=10,
            reader=lambda: 15,
        ),
        thermal_monitor=ThermalMonitor(limit_celsius=75, reader=lambda: 35.0),
        sleep_manager=SleepManager(),
        microphone_health=MicrophoneHealth(health_probe=lambda: True),
    )
    manager.register_runtime_governor(governor)

    snapshot = manager.evaluate_state()
    assert snapshot["state"] in {"LOW_BATTERY", "IDLE"}
    assert ("force_model_downgrade", "BATTERY_LOW") in governor.calls


def test_thermal_limit_triggers_cpu_budget_reduction_signal() -> None:
    governor = _SignalGovernor()
    manager = DeviceStateManager(
        battery_monitor=BatteryMonitor(reader=lambda: 80),
        thermal_monitor=ThermalMonitor(limit_celsius=75, reader=lambda: 90.0),
        sleep_manager=SleepManager(),
        microphone_health=MicrophoneHealth(health_probe=lambda: True),
    )
    manager.register_runtime_governor(governor)

    snapshot = manager.evaluate_state()
    assert snapshot["state"] == STATE_THERMAL_LIMIT
    assert ("reduce_cpu_budget", "THERMAL_LIMIT") in governor.calls


def test_sleep_state_pauses_runtime_signal() -> None:
    governor = _SignalGovernor()
    sleep_manager = SleepManager()
    assert sleep_manager.enter_sleep() is True

    manager = DeviceStateManager(
        battery_monitor=BatteryMonitor(reader=lambda: 80),
        thermal_monitor=ThermalMonitor(limit_celsius=75, reader=lambda: 35.0),
        sleep_manager=sleep_manager,
        microphone_health=MicrophoneHealth(health_probe=lambda: True),
    )
    manager.register_runtime_governor(governor)

    snapshot = manager.evaluate_state()
    assert snapshot["state"] == STATE_SLEEP
    assert ("pause_evaluation", "DEVICE_SLEEP") in governor.calls


def test_microphone_failure_escalates_to_critical_state() -> None:
    manager = DeviceStateManager(
        battery_monitor=BatteryMonitor(reader=lambda: 80),
        thermal_monitor=ThermalMonitor(limit_celsius=75, reader=lambda: 35.0),
        sleep_manager=SleepManager(),
        microphone_health=MicrophoneHealth(health_probe=lambda: False),
    )
    snapshot = manager.evaluate_state()
    assert snapshot["state"] == STATE_CRITICAL
    assert snapshot["microphone_operational"] is False


def test_no_router_import_in_hardware_layer() -> None:
    root = Path(__file__).resolve().parents[2]
    folder = root / "services" / "hardware"
    violations: list[str] = []

    for file_path in sorted(folder.rglob("*.py")):
        rel_path = file_path.relative_to(root)
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    if (
                        "router" in name
                        or name == "core.memory.lifecycle_manager"
                        or name == "core.memory.task_store"
                    ):
                        violations.append(f"{rel_path}:{node.lineno} imports {name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if (
                    "router" in module
                    or module == "core.memory.lifecycle_manager"
                    or module == "core.memory.task_store"
                ):
                    violations.append(f"{rel_path}:{node.lineno} imports from {module}")

    assert not violations, "Forbidden imports in hardware layer:\n" + "\n".join(violations)


def test_device_state_manager_signals_real_governor_for_battery_downgrade() -> None:
    governor = ResourceGovernor(
        cpu_monitor=CPUMonitor(threshold_percent=75.0, sampler=lambda: 10.0),
        memory_monitor=MemoryMonitor(threshold_mb=500.0, reader=lambda: 100.0),
        idle_unload_seconds=9999.0,
    )
    model_manager = ModelManager()
    model_manager.load_asr_model()
    governor.register_model_manager(model_manager)

    manager = DeviceStateManager(
        battery_monitor=BatteryMonitor(
            low_percent=20.0,
            critical_percent=10.0,
            reader=lambda: 15.0,
        ),
        thermal_monitor=ThermalMonitor(limit_celsius=75, reader=lambda: 35.0),
        sleep_manager=SleepManager(),
        microphone_health=MicrophoneHealth(health_probe=lambda: True),
    )
    manager.register_runtime_governor(governor)
    _ = manager.evaluate_state()
    assert model_manager.current_model_size == MODEL_TINY
