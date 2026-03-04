"""Battery signal monitor for APCOS hardware abstraction layer."""

from __future__ import annotations

from typing import Any, Callable

try:
    import psutil
except ImportError:  # pragma: no cover - optional dependency
    psutil = None


BatteryReader = Callable[[], Any | None]


def _default_battery_reader() -> Any | None:
    if psutil is None:
        return None
    try:
        return psutil.sensors_battery()
    except Exception:
        return None


class BatteryMonitor:
    """Read battery level and derive low/critical state deterministically."""

    def __init__(
        self,
        *,
        low_percent: float = 20.0,
        critical_percent: float = 10.0,
        reader: BatteryReader | None = None,
    ) -> None:
        low = float(low_percent)
        critical = float(critical_percent)
        if low < 0.0 or critical < 0.0:
            raise ValueError("battery thresholds must be >= 0")
        if critical > low:
            raise ValueError("critical_percent must be <= low_percent")
        self._low_percent = low
        self._critical_percent = critical
        self._reader = reader or _default_battery_reader

    def level_percent(self) -> float:
        """Return battery level percentage in [0, 100]."""
        reading = self._reader()
        if reading is None:
            return 100.0
        try:
            percent = float(getattr(reading, "percent", reading))
        except Exception:
            return 100.0
        return max(0.0, min(100.0, percent))

    def is_low(self) -> bool:
        """Return whether battery is at or below low threshold."""
        return self.level_percent() <= self._low_percent

    def is_critical(self) -> bool:
        """Return whether battery is at or below critical threshold."""
        return self.level_percent() <= self._critical_percent

