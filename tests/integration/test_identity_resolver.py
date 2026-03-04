from __future__ import annotations

from core.identity.identity_resolver import IdentityResolver


def test_identity_resolver_handles_login_commands() -> None:
    resolver = IdentityResolver()

    owner = resolver.resolve_identity("login owner")
    assert owner is not None
    assert owner.tier == "OWNER"

    family = resolver.resolve_identity("login family parent_1")
    assert family is not None
    assert family.tier == "FAMILY"
    assert family.user_id == "parent_1"

    guest = resolver.resolve_identity("login guest")
    assert guest is not None
    assert guest.tier == "GUEST"


def test_identity_resolver_returns_none_for_non_login_inputs() -> None:
    resolver = IdentityResolver()

    assert resolver.resolve_identity("schedule meeting tomorrow at 10") is None
    assert resolver.resolve_identity("login admin") is None


def test_identity_resolver_default_identity_is_owner() -> None:
    resolver = IdentityResolver()
    default = resolver.default_identity()

    assert default.tier == "OWNER"
    assert default.authenticated is True
