"""CPU usage monitoring utilities for APCOS runtime governance."""

from __future__ import annotations

from collections import deque
from statistics import mean
from typing import Callable

try:
    import psutil
except ImportError:  # pragma: no cover - optional runtime dependency
    psutil = None


CPUSampler = Callable[[], float]


def _default_cpu_sampler() -> float:
    if psutil is None:
        return 0.0
    try:
        return float(psutil.cpu_percent(interval=None))
    except Exception:
        return 0.0


class CPUMonitor:
    """Lightweight rolling-window CPU monitor."""

    def __init__(
        self,
        *,
        threshold_percent: float = 75.0,
        window_size: int = 5,
        sampler: CPUSampler | None = None,
    ) -> None:
        if window_size < 1:
            raise ValueError("window_size must be >= 1")
        self._threshold_percent = float(threshold_percent)
        self._window = deque(maxlen=window_size)
        self._sampler = sampler or _default_cpu_sampler

    def current_usage(self) -> float:
        """Sample and return current CPU percentage."""
        value = max(0.0, min(100.0, float(self._sampler())))
        self._window.append(value)
        return value

    def average_usage(self) -> float:
        """Return rolling average CPU usage percentage."""
        if not self._window:
            self.current_usage()
        return float(mean(self._window)) if self._window else 0.0

    def is_over_threshold(self) -> bool:
        """Return whether rolling CPU average exceeds configured threshold."""
        return self.average_usage() >= self._threshold_percent
