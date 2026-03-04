"""Configuration loading and validation for APCOS bootstrap."""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

try:
    import yaml
except ImportError as exc:  # pragma: no cover - environment dependency
    raise RuntimeError("PyYAML is required for APCOS configuration loading.") from exc


class ConfigError(ValueError):
    """Raised when bootstrap configuration is missing or malformed."""


REQUIRED_SECTIONS = ("command_router", "calibration", "proactive", "runtime", "hardware")

DEFAULTS: dict[str, Any] = {
    "command_router": {"min_confidence": 0.65, "enable_challenge_gate": True},
    "calibration": {
        "enabled": True,
        "min_threshold": 0.5,
        "max_threshold": 0.9,
        "step_size": 0.05,
    },
    "proactive": {"confidence_threshold": 0.7, "daily_limit": 3, "silent_mode": False},
    "runtime": {
        "cpu_threshold_percent": 75,
        "memory_threshold_mb": 500,
        "max_threads": 4,
        "power_mode": "NORMAL",
        "model_downgrade_enabled": True,
        "idle_unload_seconds": 300,
    },
    "hardware": {
        "battery_low_percent": 20,
        "battery_critical_percent": 10,
        "thermal_limit_celsius": 75,
        "sleep_idle_seconds": 300,
    },
}


def load_config(config_path: str | Path = "configs/default.yaml") -> Mapping[str, Any]:
    """
    Load, validate, and freeze APCOS configuration from YAML.

    Returns an immutable mapping.
    """
    path = Path(config_path)
    if not path.exists():
        raise ConfigError(f"Configuration file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Configuration file is invalid YAML: {path}") from exc
    except OSError as exc:
        raise ConfigError(f"Unable to read configuration file: {path}") from exc

    if not isinstance(loaded, Mapping):
        raise ConfigError("Configuration root must be a mapping/object.")

    _validate_required_sections(loaded)
    merged = _merge_defaults(dict(loaded))
    _validate_section_shapes(merged)
    return _deep_freeze(merged)


def _merge_defaults(loaded: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key, default_value in DEFAULTS.items():
        existing = loaded.get(key, {})
        if isinstance(default_value, dict):
            block = dict(default_value)
            if isinstance(existing, Mapping):
                block.update(dict(existing))
            merged[key] = block
        else:
            merged[key] = existing if existing is not None else default_value

    for key, value in loaded.items():
        if key not in merged:
            merged[key] = value
    return merged


def _validate_required_sections(config: Mapping[str, Any]) -> None:
    missing = [section for section in REQUIRED_SECTIONS if section not in config]
    if missing:
        raise ConfigError(f"Configuration missing required sections: {', '.join(missing)}")


def _validate_section_shapes(config: Mapping[str, Any]) -> None:
    for section in REQUIRED_SECTIONS:
        value = config.get(section)
        if not isinstance(value, Mapping):
            raise ConfigError(f"Configuration section '{section}' must be a mapping/object.")


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    return value
