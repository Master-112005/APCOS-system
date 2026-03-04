"""Session-scoped identity resolver for CLI login commands (stub)."""

from __future__ import annotations

import re

from core.identity.identity_context import IdentityContext

LOGIN_PATTERN = re.compile(
    r"^\s*login\s+(?P<tier>owner|family|guest)(?:\s+(?P<user_id>[A-Za-z0-9_.-]+))?\s*$",
    re.IGNORECASE,
)


class IdentityResolver:
    """Resolve CLI identity commands into immutable identity contexts."""

    def default_identity(self) -> IdentityContext:
        """Return default authenticated owner context for local session."""
        return IdentityContext(user_id="owner_session", tier="OWNER", authenticated=True)

    def resolve_identity(self, input_str: str) -> IdentityContext | None:
        """
        Resolve login commands into IdentityContext.

        Returns None for non-login or invalid login commands.
        """
        match = LOGIN_PATTERN.match((input_str or "").strip())
        if not match:
            return None

        tier = match.group("tier").upper()
        supplied_user = match.group("user_id")
        user_id = supplied_user or f"{tier.lower()}_session"
        return IdentityContext(user_id=user_id, tier=tier, authenticated=True)
