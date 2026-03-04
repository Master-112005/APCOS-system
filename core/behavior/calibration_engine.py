"""Deterministic proactive-threshold calibration logic."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

try:
    import yaml
except ImportError:  # pragma: no cover - exercised through default fallback
    yaml = None

from core.behavior.acceptance_tracker import AcceptanceMetrics


@dataclass(frozen=True)
class CalibrationConfig:
    """Configuration model for threshold calibration."""

    enabled: bool = True
    min_threshold: float = 0.5
    max_threshold: float = 0.9
    step_size: float = 0.05


class CalibrationEngine:
    """
    Deterministic controller for proactive confidence threshold adaptation.

    This module only adjusts numeric thresholds; it never triggers proactive
    suggestions, mutates task data, or touches lifecycle/router layers.
    """

    def __init__(self, *, config_path: str | Path = "configs/default.yaml") -> None:
        self._config = self._load_config(Path(config_path))

    @property
    def config(self) -> CalibrationConfig:
        """Expose calibration configuration for observability/testing."""
        return self._config

    def update_threshold(
        self,
        current_threshold: float,
        metrics: AcceptanceMetrics | Mapping[str, Any],
    ) -> float:
        """
        Update proactive confidence threshold using bounded deterministic math.

        Rules:
        - If acceptance_rate > 0.70, lower threshold by step (more proactive).
        - If rejection_rate > 0.60, increase threshold by step (less proactive).
        - If override_rate > 0.40, increase threshold by step (respect overrides).
        - Always clamp to [min_threshold, max_threshold].
        - If disabled, return clamped current threshold unchanged.
        """
        cfg = self._config
        clamped_current = self._clamp(current_threshold, cfg.min_threshold, cfg.max_threshold)

        if not cfg.enabled:
            return clamped_current

        acceptance_rate, rejection_rate, override_rate = self._extract_rates(metrics)

        delta = 0.0
        if rejection_rate > 0.60 or override_rate > 0.40:
            delta += cfg.step_size
        elif acceptance_rate > 0.70:
            delta -= cfg.step_size

        adjusted = clamped_current + delta
        return self._clamp(adjusted, cfg.min_threshold, cfg.max_threshold)

    @staticmethod
    def _extract_rates(metrics: AcceptanceMetrics | Mapping[str, Any]) -> tuple[float, float, float]:
        if isinstance(metrics, AcceptanceMetrics):
            accepted = metrics.accepted
            rejected = metrics.rejected
            ignored = metrics.ignored
            overrides = metrics.overrides
            acceptance_rate = metrics.acceptance_rate
        else:
            accepted = int(metrics.get("accepted", 0))
            rejected = int(metrics.get("rejected", 0))
            ignored = int(metrics.get("ignored", 0))
            overrides = int(metrics.get("overrides", 0))
            acceptance_rate = float(metrics.get("acceptance_rate", 0.0))

        attempts = max(0, accepted + rejected + ignored)
        rejection_rate = (rejected / attempts) if attempts else 0.0
        override_rate = (overrides / attempts) if attempts else 0.0
        return acceptance_rate, rejection_rate, override_rate

    @staticmethod
    def _clamp(value: float, lower: float, upper: float) -> float:
        return max(lower, min(upper, float(value)))

    @staticmethod
    def _load_config(path: Path) -> CalibrationConfig:
        defaults = CalibrationConfig()
        if not path.exists() or yaml is None:
            return defaults

        try:
            with path.open("r", encoding="utf-8") as handle:
                parsed = yaml.safe_load(handle) or {}
        except Exception:
            return defaults

        section = parsed.get("calibration", {})
        if not isinstance(section, Mapping):
            return defaults

        enabled = bool(section.get("enabled", defaults.enabled))
        min_threshold = float(section.get("min_threshold", defaults.min_threshold))
        max_threshold = float(section.get("max_threshold", defaults.max_threshold))
        step_size = float(section.get("step_size", defaults.step_size))

        if min_threshold > max_threshold:
            min_threshold, max_threshold = defaults.min_threshold, defaults.max_threshold
        if step_size <= 0:
            step_size = defaults.step_size

        return CalibrationConfig(
            enabled=enabled,
            min_threshold=min_threshold,
            max_threshold=max_threshold,
            step_size=step_size,
        )
