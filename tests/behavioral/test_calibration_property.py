from __future__ import annotations

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from core.behavior.calibration_engine import CalibrationEngine


@settings(max_examples=300, deadline=None)
@given(
    current_threshold=st.floats(
        min_value=0.5,
        max_value=0.9,
        allow_nan=False,
        allow_infinity=False,
    ),
    acceptance_rate=st.floats(
        min_value=0.0,
        max_value=1.0,
        allow_nan=False,
        allow_infinity=False,
    ),
    rejection_rate=st.floats(
        min_value=0.0,
        max_value=1.0,
        allow_nan=False,
        allow_infinity=False,
    ),
    overrides=st.integers(min_value=0, max_value=100),
)
def test_calibration_output_is_always_bounded(
    current_threshold: float,
    acceptance_rate: float,
    rejection_rate: float,
    overrides: int,
) -> None:
    engine = CalibrationEngine(config_path="configs/default.yaml")
    total = 100
    rejected = int(rejection_rate * total)
    accepted = int(acceptance_rate * (total - rejected))
    ignored = total - rejected - accepted

    metrics = {
        "accepted": accepted,
        "rejected": rejected,
        "ignored": ignored,
        "overrides": min(overrides, total),
        "acceptance_rate": acceptance_rate,
    }
    updated = engine.update_threshold(current_threshold, metrics)
    cfg = engine.config

    assert math.isfinite(updated)
    assert not math.isnan(updated)
    assert updated >= 0.0
    assert cfg.min_threshold <= updated <= cfg.max_threshold
