"""Thermal signal monitor for APCOS hardware abstraction layer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Callable

try:
    import psutil
except ImportError:  # pragma: no cover - optional dependency
    psutil = None


TemperatureReader = Callable[[], Any]


def _default_temperature_reader() -> dict[str, list[Any]]:
    if psutil is None:
        return {}
    try:
        return psutil.sensors_temperatures() or {}
    except Exception:
        return {}


class ThermalMonitor:
    """Read CPU temperature and detect thermal pressure."""

    def __init__(
        self,
        *,
        limit_celsius: float = 75.0,
        reader: TemperatureReader | None = None,
    ) -> None:
        self._limit_celsius = float(limit_celsius)
        self._reader = reader or _default_temperature_reader

    def temperature_celsius(self) -> float:
        """Return current representative CPU temperature in Celsius."""
        payload = self._reader()
        samples: list[float] = []

        if isinstance(payload, Mapping):
            for entries in payload.values():
                samples.extend(self._extract_samples(entries))
        else:
            samples.extend(self._extract_samples(payload))

        if not samples:
            return 0.0
        return max(0.0, float(max(samples)))

    def is_over_limit(self) -> bool:
        """Return whether temperature exceeds configured limit."""
        return self.temperature_celsius() >= self._limit_celsius

    @staticmethod
    def _extract_samples(payload: Any) -> list[float]:
        if payload is None:
            return []
        if isinstance(payload, (int, float)):
            return [float(payload)]
        if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
            values: list[float] = []
            for item in payload:
                values.extend(ThermalMonitor._extract_samples(item))
            return values

        try:
            value = float(getattr(payload, "current"))
            return [value]
        except Exception:
            return []

