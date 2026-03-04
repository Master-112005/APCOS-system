from __future__ import annotations

from core.identity.access_control import AccessControl
from core.identity.identity_context import IdentityContext


def test_owner_has_full_crud_and_strategy_access() -> None:
    access = AccessControl()
    owner = IdentityContext(user_id="owner_session", tier="OWNER", authenticated=True)

    assert access.is_allowed("schedule_task", owner) is True
    assert access.is_allowed("mark_completed", owner) is True
    assert access.is_allowed("cancel_task", owner) is True
    assert access.is_allowed("strategy", owner) is True


def test_family_cannot_archive_or_create() -> None:
    access = AccessControl()
    family = IdentityContext(user_id="family_session", tier="FAMILY", authenticated=True)

    assert access.is_allowed("schedule_task", family) is False
    assert access.is_allowed("mark_completed", family) is True
    assert access.is_allowed("cancel_task", family) is False
    assert access.is_allowed("strategy", family) is True


def test_guest_can_only_use_strategy() -> None:
    access = AccessControl()
    guest = IdentityContext(user_id="guest_session", tier="GUEST", authenticated=True)

    assert access.is_allowed("schedule_task", guest) is False
    assert access.is_allowed("mark_completed", guest) is False
    assert access.is_allowed("cancel_task", guest) is False
    assert access.is_allowed("strategy", guest) is True


def test_unauthenticated_identity_has_no_access() -> None:
    access = AccessControl()
    owner = IdentityContext(user_id="owner_session", tier="OWNER", authenticated=False)

    assert access.is_allowed("schedule_task", owner) is False
    assert access.is_allowed("strategy", owner) is False
