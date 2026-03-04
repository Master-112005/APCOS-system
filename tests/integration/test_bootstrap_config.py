from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

import pytest

from apcos.bootstrap.config_loader import ConfigError, load_config


def test_load_config_valid_and_immutable() -> None:
    config = load_config("configs/default.yaml")

    assert isinstance(config, MappingProxyType)
    assert "command_router" in config
    assert "calibration" in config
    assert "proactive" in config
    assert "runtime" in config
    assert "hardware" in config

    with pytest.raises(TypeError):
        config["new_key"] = "value"  # type: ignore[index]


def test_load_config_missing_required_section_raises_clean_error(tmp_path: Path) -> None:
    config_path = tmp_path / "missing.yaml"
    config_path.write_text(
        "\n".join(
            [
                "command_router:",
                "  min_confidence: 0.65",
                "proactive:",
                "  confidence_threshold: 0.7",
                "  daily_limit: 3",
                "  silent_mode: false",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError) as exc:
        load_config(config_path)
    assert "missing required sections" in str(exc.value).lower()
