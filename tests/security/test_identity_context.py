from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from core.identity.identity_context import IdentityContext


def test_identity_context_is_immutable_and_normalized() -> None:
    context = IdentityContext(user_id=" user_1 ", tier="owner", authenticated=True)
    assert context.user_id == "user_1"
    assert context.tier == "OWNER"
    assert context.authenticated is True

    with pytest.raises(FrozenInstanceError):
        context.tier = "GUEST"  # type: ignore[misc]


def test_identity_context_rejects_invalid_tier() -> None:
    with pytest.raises(ValueError):
        IdentityContext(user_id="user_1", tier="ADMIN", authenticated=True)
