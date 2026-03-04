from __future__ import annotations

from core.behavior.memory_monitor import MemoryMonitor


def test_memory_monitor_detects_pressure() -> None:
    samples = iter([100.0, 550.0])
    monitor = MemoryMonitor(threshold_mb=500.0, reader=lambda: next(samples))

    assert monitor.current_usage_mb() == 100.0
    assert monitor.is_pressure_high() is True


def test_memory_monitor_clamps_negative_usage() -> None:
    monitor = MemoryMonitor(threshold_mb=1.0, reader=lambda: -100.0)
    assert monitor.current_usage_mb() == 0.0
