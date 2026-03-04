"""Audio capture boundary for APCOS voice interaction (stub)."""

from __future__ import annotations


def capture_audio() -> bytes:
    """
    Capture a single audio frame.

    Stage 6 uses a deterministic stub payload and does not persist audio.
    """
    return b"text:"
