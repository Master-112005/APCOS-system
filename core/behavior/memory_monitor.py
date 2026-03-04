"""Process memory usage monitoring for APCOS runtime governance."""

from __future__ import annotations

import os
from typing import Callable

try:
    import psutil
except ImportError:  # pragma: no cover - optional runtime dependency
    psutil = None


MemoryReader = Callable[[], float]


def _default_memory_reader() -> float:
    if psutil is None:
        return 0.0
    try:
        process = psutil.Process(os.getpid())
        return float(process.memory_info().rss / (1024 * 1024))
    except Exception:
        return 0.0


class MemoryMonitor:
    """Lightweight process RSS monitor with threshold checks."""

    def __init__(
        self,
        *,
        threshold_mb: float = 500.0,
        reader: MemoryReader | None = None,
    ) -> None:
        self._threshold_mb = float(threshold_mb)
        self._reader = reader or _default_memory_reader

    def current_usage_mb(self) -> float:
        """Return current process memory usage in MB (RSS)."""
        return max(0.0, float(self._reader()))

    def is_pressure_high(self) -> bool:
        """Return whether memory usage exceeds configured threshold."""
        return self.current_usage_mb() >= self._threshold_mb
