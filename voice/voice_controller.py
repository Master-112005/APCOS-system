"""Voice runtime loop for APCOS Stage 6."""

from __future__ import annotations

from typing import Callable
import time

from voice.voice_session import VoiceSession


def run_voice_loop(
    session: VoiceSession,
    *,
    output_func: Callable[[str], None] = print,
    sleep_func: Callable[[float], None] = time.sleep,
    poll_interval: float = 0.05,
    stop_condition: Callable[[], bool] | None = None,
) -> None:
    """
    Run continuous wake-word polling loop and emit voice responses.

    The loop sleeps between polls to avoid busy-spin CPU usage.
    """
    output_func("APCOS Voice ready. Waiting for wake word.")
    while True:
        if stop_condition is not None and stop_condition():
            output_func("Exiting APCOS voice loop.")
            return

        try:
            response = session.run_once()
        except KeyboardInterrupt:
            output_func("\nVoice session interrupted. Exiting APCOS voice loop.")
            return
        except Exception:
            output_func("I could not execute that due to an internal system error.")
            sleep_func(poll_interval)
            continue

        if response:
            output_func(response)
        sleep_func(poll_interval)
