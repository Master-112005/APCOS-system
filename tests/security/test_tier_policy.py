from __future__ import annotations

import pytest

from core.identity.tier_policy import PERMISSIONS


def test_tier_policy_matrix_is_correct() -> None:
    assert PERMISSIONS["OWNER"] == frozenset({"CREATE", "COMPLETE", "ARCHIVE", "STRATEGY"})
    assert PERMISSIONS["FAMILY"] == frozenset({"COMPLETE", "STRATEGY"})
    assert PERMISSIONS["GUEST"] == frozenset({"STRATEGY"})


def test_tier_policy_is_immutable() -> None:
    with pytest.raises(TypeError):
        PERMISSIONS["OWNER"] = frozenset()  # type: ignore[index]
