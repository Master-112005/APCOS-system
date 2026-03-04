"""Identity context model for APCOS session-level access control."""

from __future__ import annotations

from dataclasses import dataclass

VALID_TIERS = {"OWNER", "FAMILY", "GUEST"}


@dataclass(frozen=True, slots=True)
class IdentityContext:
    """Immutable identity context for the active session user."""

    user_id: str
    tier: str
    authenticated: bool

    def __post_init__(self) -> None:
        user_id = self.user_id.strip()
        tier = self.tier.strip().upper()

        if not user_id:
            raise ValueError("user_id must not be empty")
        if tier not in VALID_TIERS:
            raise ValueError(f"Unsupported identity tier: {self.tier}")

        object.__setattr__(self, "user_id", user_id)
        object.__setattr__(self, "tier", tier)
