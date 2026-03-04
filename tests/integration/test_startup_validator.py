from __future__ import annotations

from pathlib import Path

import pytest

from apcos.bootstrap.config_loader import load_config
from apcos.bootstrap.startup_validator import StartupValidationError, validate_startup


def test_startup_validator_passes_with_valid_project_layout() -> None:
    config = load_config("configs/default.yaml")
    validate_startup(config, project_root=Path("."))


def test_startup_validator_fails_for_missing_directories(tmp_path: Path) -> None:
    config = load_config("configs/default.yaml")
    with pytest.raises(StartupValidationError) as exc:
        validate_startup(config, project_root=tmp_path)
    assert "missing required directories" in str(exc.value).lower()


def test_startup_validator_fails_for_missing_config_section() -> None:
    with pytest.raises(StartupValidationError) as exc:
        validate_startup({"command_router": {}}, project_root=Path("."))
    assert "missing required sections" in str(exc.value).lower()
