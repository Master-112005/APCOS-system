"""Goal-alignment challenge logic with one-challenge guardrail."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any


class ChallengeLogic:
    """
    Challenge misaligned actions once, never force user decisions.

    Rules:
    - at most one challenge per task+action key
    - do not challenge if user already overrode
    - never repeat after explicit rejection
    """

    def __init__(self, *, challenge_threshold: float = 0.5) -> None:
        if challenge_threshold < 0.0 or challenge_threshold > 1.0:
            raise ValueError("challenge_threshold must be between 0 and 1")
        self._challenge_threshold = challenge_threshold
        self._challenged_keys: set[tuple[int, str]] = set()
        self._rejected_keys: set[tuple[int, str]] = set()

    def evaluate(
        self,
        *,
        task_id: int,
        proposed_action: str,
        declared_goal: str,
        alignment_score: float,
        user_overrode: bool = False,
    ) -> dict[str, Any] | None:
        """Return challenge suggestion when alignment is below threshold."""
        action_key = self._normalize_action(proposed_action)
        cache_key = (task_id, action_key)

        if user_overrode:
            return None
        if cache_key in self._rejected_keys:
            return None
        if cache_key in self._challenged_keys:
            return None
        if alignment_score >= self._challenge_threshold:
            return None

        self._challenged_keys.add(cache_key)
        challenge_id = self._challenge_id(task_id, action_key)
        return {
            "challenge_id": challenge_id,
            "task_id": task_id,
            "action": proposed_action,
            "goal": declared_goal,
            "alignment_score": float(alignment_score),
            "message": "This action appears misaligned with your stated goal. Continue anyway?",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def record_response(self, *, task_id: int, proposed_action: str, accepted: bool) -> None:
        """Record challenge response to enforce no-repeat behavior."""
        action_key = self._normalize_action(proposed_action)
        cache_key = (task_id, action_key)
        if not accepted:
            self._rejected_keys.add(cache_key)

    @staticmethod
    def _normalize_action(action: str) -> str:
        return " ".join(action.lower().strip().split())

    @staticmethod
    def _challenge_id(task_id: int, action_key: str) -> str:
        token = f"{task_id}:{action_key}".encode("utf-8")
        digest = hashlib.sha1(token).hexdigest()[:12]
        return f"challenge-{digest}"
