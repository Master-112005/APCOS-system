from __future__ import annotations

from services.hardware.thermal_monitor import ThermalMonitor


def test_thermal_monitor_detects_over_limit() -> None:
    class Sample:
        current = 81.0

    monitor = ThermalMonitor(limit_celsius=75.0, reader=lambda: {"cpu": [Sample()]})
    assert monitor.temperature_celsius() == 81.0
    assert monitor.is_over_limit() is True


def test_thermal_monitor_handles_missing_sensor_payload() -> None:
    monitor = ThermalMonitor(limit_celsius=75.0, reader=lambda: {})
    assert monitor.temperature_celsius() == 0.0
    assert monitor.is_over_limit() is False

