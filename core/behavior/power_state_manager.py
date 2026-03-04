"""Power-state management for runtime governor decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PowerMode(str, Enum):
    """Supported runtime power modes."""

    NORMAL = "NORMAL"
    LOW_POWER = "LOW_POWER"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class PowerStateSnapshot:
    """Immutable power mode evaluation result."""

    mode: PowerMode
    cpu_over_threshold: bool
    memory_pressure_high: bool


class PowerStateManager:
    """Deterministic power-state transitions from resource pressure inputs."""

    def __init__(self, *, initial_mode: str = "NORMAL") -> None:
        try:
            self._mode = PowerMode(initial_mode)
        except ValueError:
            self._mode = PowerMode.NORMAL

    def current_mode(self) -> PowerMode:
        """Return current power mode."""
        return self._mode

    def update_mode(self, *, cpu_over_threshold: bool, memory_pressure_high: bool) -> PowerMode:
        """Update mode from CPU/memory pressure state."""
        if cpu_over_threshold and memory_pressure_high:
            self._mode = PowerMode.CRITICAL
        elif cpu_over_threshold or memory_pressure_high:
            self._mode = PowerMode.LOW_POWER
        else:
            self._mode = PowerMode.NORMAL
        return self._mode

    def snapshot(self, *, cpu_over_threshold: bool, memory_pressure_high: bool) -> PowerStateSnapshot:
        """Update and return immutable power-state snapshot."""
        mode = self.update_mode(
            cpu_over_threshold=cpu_over_threshold,
            memory_pressure_high=memory_pressure_high,
        )
        return PowerStateSnapshot(
            mode=mode,
            cpu_over_threshold=cpu_over_threshold,
            memory_pressure_high=memory_pressure_high,
        )
