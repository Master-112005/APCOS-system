"""Advisory archival policy hints for storage authority requests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArchivalRecommendation:
    """Pure advisory recommendation for retention intent."""

    should_archive: bool
    reason_code: str
    ttl_days: int | None = None


def recommend_archival(*, state: str, age_days: int, completed: bool) -> ArchivalRecommendation:
    """
    Produce deterministic archival recommendation.

    Stage 15 note:
    - This function does not decide mutation authority.
    - Rust secure storage policy remains the final storage decision maker.
    """
    normalized_state = state.strip().upper()
    if normalized_state == "ARCHIVED":
        return ArchivalRecommendation(
            should_archive=True,
            reason_code="ALREADY_ARCHIVED",
            ttl_days=30,
        )
    if completed and age_days >= 30:
        return ArchivalRecommendation(
            should_archive=True,
            reason_code="COMPLETED_RETENTION_ELIGIBLE",
            ttl_days=30,
        )
    return ArchivalRecommendation(
        should_archive=False,
        reason_code="ACTIVE_RETENTION",
        ttl_days=None,
    )
