"""Identity-based access control checks for APCOS intent execution."""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from core.identity.identity_context import IdentityContext
from core.identity.tier_policy import PERMISSIONS

INTENT_TO_ACTION: Mapping[str, str] = MappingProxyType(
    {
        "create_task": "CREATE",
        "schedule_task": "CREATE",
        "complete_task": "COMPLETE",
        "mark_completed": "COMPLETE",
        "archive_task": "ARCHIVE",
        "cancel_task": "ARCHIVE",
        "strategy": "STRATEGY",
    }
)


class AccessControl:
    """Deterministic permission checks based on identity tier policy."""

    def is_allowed(self, intent_type: str, identity: IdentityContext) -> bool:
        """Return True when tier policy permits the mapped intent action."""
        if not identity.authenticated:
            return False

        normalized_intent = (intent_type or "").strip().lower()
        action = INTENT_TO_ACTION.get(normalized_intent)
        if action is None:
            return False

        allowed_actions = PERMISSIONS.get(identity.tier, frozenset())
        return action in allowed_actions
