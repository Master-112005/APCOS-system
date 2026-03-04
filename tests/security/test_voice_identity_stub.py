from __future__ import annotations

from voice.voice_identity_stub import resolve_voice_identity


def test_voice_identity_stub_defaults_to_owner() -> None:
    identity = resolve_voice_identity(b"text:Schedule planning tomorrow at 10")
    assert identity.tier == "OWNER"
    assert identity.authenticated is True


def test_voice_identity_stub_resolves_guest_and_family_markers() -> None:
    guest = resolve_voice_identity(b"tier:guest;text:/strategy plan my week")
    family = resolve_voice_identity(b"tier:family;text:Mark workout completed")

    assert guest.tier == "GUEST"
    assert family.tier == "FAMILY"
    assert guest.user_id.endswith("_voice_session")
    assert family.user_id.endswith("_voice_session")
