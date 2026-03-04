from __future__ import annotations

from core.behavior.cpu_monitor import CPUMonitor


def test_cpu_monitor_reports_threshold_crossing() -> None:
    samples = iter([10.0, 20.0, 90.0, 95.0, 92.0])
    monitor = CPUMonitor(
        threshold_percent=75.0,
        window_size=3,
        sampler=lambda: next(samples),
    )

    monitor.current_usage()
    monitor.current_usage()
    monitor.current_usage()
    assert monitor.is_over_threshold() is False

    monitor.current_usage()
    monitor.current_usage()
    assert monitor.is_over_threshold() is True


def test_cpu_monitor_clamps_invalid_sample_values() -> None:
    samples = iter([-10.0, 150.0])
    monitor = CPUMonitor(threshold_percent=90.0, sampler=lambda: next(samples))

    assert monitor.current_usage() == 0.0
    assert monitor.current_usage() == 100.0
