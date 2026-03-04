from __future__ import annotations

from types import SimpleNamespace

from services.hardware.battery_monitor import BatteryMonitor


def test_battery_monitor_detects_low_and_critical() -> None:
    monitor = BatteryMonitor(
        low_percent=20,
        critical_percent=10,
        reader=lambda: SimpleNamespace(percent=9.0),
    )

    assert monitor.level_percent() == 9.0
    assert monitor.is_low() is True
    assert monitor.is_critical() is True


def test_battery_monitor_defaults_to_safe_when_sensor_missing() -> None:
    monitor = BatteryMonitor(reader=lambda: None)
    assert monitor.level_percent() == 100.0
    assert monitor.is_low() is False
    assert monitor.is_critical() is False

