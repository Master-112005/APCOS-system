"""Voice identity resolver stub for APCOS Stage 6."""

from __future__ import annotations

from core.identity.identity_context import IdentityContext


def resolve_voice_identity(
    audio: bytes | None = None,
    *,
    transcript: str | None = None,
) -> IdentityContext:
    """
    Resolve a deterministic identity tier from audio markers.

    Marker examples:
    - `tier:guest`  -> GUEST
    - `tier:family` -> FAMILY
    - default       -> OWNER
    """
    parts: list[str] = []
    if transcript:
        parts.append(transcript.lower())
    if audio:
        parts.append(audio.decode("utf-8", errors="ignore").lower())
    payload = " ".join(parts)
    if "tier:guest" in payload:
        tier = "GUEST"
    elif "tier:family" in payload:
        tier = "FAMILY"
    else:
        tier = "OWNER"

    return IdentityContext(
        user_id=f"{tier.lower()}_voice_session",
        tier=tier,
        authenticated=True,
    )
