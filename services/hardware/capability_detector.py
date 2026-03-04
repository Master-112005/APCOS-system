"""Runtime hardware capability detector for APCOS."""

from __future__ import annotations

import os
from typing import Callable

try:
    import psutil
except ImportError:  # pragma: no cover - optional dependency
    psutil = None


BoolProbe = Callable[[], bool]
IntProbe = Callable[[], int]


def _default_cpu_probe() -> int:
    return max(1, int(os.cpu_count() or 1))


def _default_ram_probe() -> int:
    if psutil is None:
        return 0
    try:
        return int(psutil.virtual_memory().total)
    except Exception:
        return 0


def _default_battery_probe() -> bool:
    if psutil is None:
        return False
    try:
        return psutil.sensors_battery() is not None
    except Exception:
        return False


def _default_gpu_probe() -> bool:
    # Stage 9 keeps GPU detection lightweight and deterministic.
    return str(os.getenv("APCOS_HAS_GPU", "0")).strip() in {"1", "true", "TRUE", "yes", "YES"}


def _default_microphone_probe() -> bool:
    # Microphone backend probing is stubbed in Stage 9.
    return True


class CapabilityDetector:
    """Detect host hardware capabilities for startup-time runtime sizing."""

    def __init__(
        self,
        *,
        cpu_probe: IntProbe | None = None,
        ram_probe: IntProbe | None = None,
        battery_probe: BoolProbe | None = None,
        microphone_probe: BoolProbe | None = None,
        gpu_probe: BoolProbe | None = None,
    ) -> None:
        self._cpu_probe = cpu_probe or _default_cpu_probe
        self._ram_probe = ram_probe or _default_ram_probe
        self._battery_probe = battery_probe or _default_battery_probe
        self._microphone_probe = microphone_probe or _default_microphone_probe
        self._gpu_probe = gpu_probe or _default_gpu_probe

    def detect(self) -> dict[str, int | bool]:
        """Return structured capability facts without side effects."""
        cpu_cores = max(1, int(self._cpu_probe()))
        total_ram_bytes = max(0, int(self._ram_probe()))
        total_ram_mb = int(total_ram_bytes / (1024 * 1024)) if total_ram_bytes else 0

        return {
            "cpu_cores": cpu_cores,
            "total_ram_mb": total_ram_mb,
            "has_battery": bool(self._battery_probe()),
            "has_microphone": bool(self._microphone_probe()),
            "has_gpu": bool(self._gpu_probe()),
        }

