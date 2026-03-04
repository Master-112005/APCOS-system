from __future__ import annotations

from services.hardware.capability_detector import CapabilityDetector


def test_capability_detection_returns_expected_structure() -> None:
    detector = CapabilityDetector(
        cpu_probe=lambda: 8,
        ram_probe=lambda: 8 * 1024 * 1024 * 1024,
        battery_probe=lambda: True,
        microphone_probe=lambda: False,
        gpu_probe=lambda: True,
    )

    capabilities = detector.detect()
    assert capabilities == {
        "cpu_cores": 8,
        "total_ram_mb": 8192,
        "has_battery": True,
        "has_microphone": False,
        "has_gpu": True,
    }

