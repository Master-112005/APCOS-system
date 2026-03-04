from __future__ import annotations

import pytest

from core.behavior.acceptance_tracker import AcceptanceMetrics
from core.behavior.calibration_engine import CalibrationEngine


def test_threshold_decreases_with_high_acceptance_rate() -> None:
    engine = CalibrationEngine(config_path="configs/default.yaml")
    current = 0.7
    metrics = AcceptanceMetrics(
        accepted=8,
        rejected=1,
        ignored=1,
        overrides=0,
        acceptance_rate=0.8,
    )

    updated = engine.update_threshold(current, metrics)
    assert updated == pytest.approx(0.65)


def test_threshold_increases_with_high_rejection_rate() -> None:
    engine = CalibrationEngine(config_path="configs/default.yaml")
    current = 0.7
    metrics = AcceptanceMetrics(
        accepted=1,
        rejected=7,
        ignored=2,
        overrides=0,
        acceptance_rate=0.1,
    )

    updated = engine.update_threshold(current, metrics)
    assert updated == pytest.approx(0.75)


def test_threshold_bounds_are_enforced() -> None:
    engine = CalibrationEngine(config_path="configs/default.yaml")

    high_acceptance = AcceptanceMetrics(
        accepted=10,
        rejected=0,
        ignored=0,
        overrides=0,
        acceptance_rate=1.0,
    )
    low_value = engine.update_threshold(0.5, high_acceptance)
    assert low_value == pytest.approx(0.5)

    high_rejection = AcceptanceMetrics(
        accepted=0,
        rejected=10,
        ignored=0,
        overrides=0,
        acceptance_rate=0.0,
    )
    high_value = engine.update_threshold(0.9, high_rejection)
    assert high_value == pytest.approx(0.9)


def test_disabled_calibration_results_in_no_change(tmp_path) -> None:
    config_path = tmp_path / "default.yaml"
    config_path.write_text(
        "\n".join(
            [
                "calibration:",
                "  enabled: false",
                "  min_threshold: 0.5",
                "  max_threshold: 0.9",
                "  step_size: 0.05",
            ]
        ),
        encoding="utf-8",
    )

    engine = CalibrationEngine(config_path=config_path)
    metrics = {
        "accepted": 8,
        "rejected": 1,
        "ignored": 1,
        "overrides": 0,
        "acceptance_rate": 0.8,
    }
    updated = engine.update_threshold(0.72, metrics)
    assert updated == pytest.approx(0.72)
