"""Device-level state aggregation and governor signaling for APCOS HAL."""

from __future__ import annotations

from threading import Lock
import time
from typing import Any

from services.hardware.battery_monitor import BatteryMonitor
from services.hardware.microphone_health import MicrophoneHealth
from services.hardware.sleep_manager import SleepManager
from services.hardware.thermal_monitor import ThermalMonitor

STATE_POWERED_ON = "POWERED_ON"
STATE_IDLE = "IDLE"
STATE_SLEEP = "SLEEP"
STATE_LOW_BATTERY = "LOW_BATTERY"
STATE_THERMAL_LIMIT = "THERMAL_LIMIT"
STATE_CRITICAL = "CRITICAL"


class DeviceStateManager:
    """Aggregate HAL signals and relay pressure events to runtime governor."""

    def __init__(
        self,
        *,
        battery_monitor: BatteryMonitor,
        thermal_monitor: ThermalMonitor,
        sleep_manager: SleepManager,
        microphone_health: MicrophoneHealth,
    ) -> None:
        self._battery_monitor = battery_monitor
        self._thermal_monitor = thermal_monitor
        self._sleep_manager = sleep_manager
        self._microphone_health = microphone_health
        self._state = STATE_POWERED_ON
        self._governor: Any | None = None
        self._lock = Lock()

    def register_runtime_governor(self, governor: Any) -> None:
        """Register runtime governor receiver for hardware pressure signals."""
        self._governor = governor

    def current_state(self) -> str:
        """Return current evaluated device state."""
        with self._lock:
            return self._state

    def evaluate_state(self) -> dict[str, Any]:
        """Evaluate hardware state once and emit deterministic signal actions."""
        started_at = time.perf_counter()
        battery_percent = self._battery_monitor.level_percent()
        battery_low = self._battery_monitor.is_low()
        battery_critical = self._battery_monitor.is_critical()
        thermal_celsius = self._thermal_monitor.temperature_celsius()
        thermal_over = self._thermal_monitor.is_over_limit()
        sleeping = self._sleep_manager.is_sleeping()
        microphone_ok = self._microphone_health.is_operational()

        if sleeping:
            new_state = STATE_SLEEP
        elif battery_critical or not microphone_ok:
            new_state = STATE_CRITICAL
        elif thermal_over:
            new_state = STATE_THERMAL_LIMIT
        elif battery_low:
            new_state = STATE_LOW_BATTERY
        else:
            new_state = STATE_IDLE

        actions = tuple(
            self._signal_governor(
                sleeping=sleeping,
                battery_low=battery_low,
                battery_critical=battery_critical,
                thermal_over=thermal_over,
                microphone_ok=microphone_ok,
            )
        )

        with self._lock:
            self._state = new_state

        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        return {
            "state": new_state,
            "battery_percent": battery_percent,
            "thermal_celsius": thermal_celsius,
            "microphone_operational": microphone_ok,
            "actions": actions,
            "elapsed_ms": elapsed_ms,
        }

    def _signal_governor(
        self,
        *,
        sleeping: bool,
        battery_low: bool,
        battery_critical: bool,
        thermal_over: bool,
        microphone_ok: bool,
    ) -> list[str]:
        governor = self._governor
        if governor is None:
            return []

        actions: list[str] = []

        if sleeping:
            if hasattr(governor, "pause_evaluation"):
                governor.pause_evaluation(reason="DEVICE_SLEEP")
                actions.append("GOVERNOR_PAUSED")
        elif hasattr(governor, "resume_evaluation"):
            governor.resume_evaluation(reason="DEVICE_WAKE")
            actions.append("GOVERNOR_RESUMED")

        if thermal_over and hasattr(governor, "reduce_cpu_budget"):
            governor.reduce_cpu_budget(reason="THERMAL_LIMIT")
            actions.append("CPU_BUDGET_REDUCED")

        if (battery_low or battery_critical) and hasattr(governor, "force_model_downgrade"):
            reason = "BATTERY_CRITICAL" if battery_critical else "BATTERY_LOW"
            governor.force_model_downgrade(reason=reason)
            actions.append("MODEL_DOWNGRADE_REQUESTED")

        if battery_critical and hasattr(governor, "force_model_unload"):
            governor.force_model_unload(reason="BATTERY_CRITICAL")
            actions.append("MODEL_UNLOAD_REQUESTED")

        if not microphone_ok and hasattr(governor, "pause_evaluation"):
            governor.pause_evaluation(reason="MICROPHONE_FAILURE")
            actions.append("GOVERNOR_PAUSED_MIC_FAILURE")

        return actions

