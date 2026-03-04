from __future__ import annotations

from voice.voice_controller import run_voice_loop


class SequencedSession:
    def __init__(self, responses: list[str | None]) -> None:
        self._responses = responses
        self._index = 0

    def run_once(self) -> str | None:
        if self._index >= len(self._responses):
            return None
        value = self._responses[self._index]
        self._index += 1
        return value


class InterruptingSession:
    def run_once(self) -> str | None:
        raise KeyboardInterrupt


def test_voice_controller_loop_outputs_responses_and_exits() -> None:
    session = SequencedSession([None, "Voice response ready", None])
    outputs: list[str] = []
    sleeps: list[float] = []
    counter = {"value": 0}

    def stop_condition() -> bool:
        counter["value"] += 1
        return counter["value"] > 3

    run_voice_loop(
        session,
        output_func=outputs.append,
        sleep_func=sleeps.append,
        poll_interval=0.01,
        stop_condition=stop_condition,
    )

    joined = "\n".join(outputs).lower()
    assert "voice ready" in joined
    assert "voice response ready" in joined
    assert "exiting apcos voice loop" in joined
    assert len(sleeps) >= 3


def test_voice_controller_handles_keyboard_interrupt_gracefully() -> None:
    outputs: list[str] = []
    sleeps: list[float] = []

    run_voice_loop(
        InterruptingSession(),
        output_func=outputs.append,
        sleep_func=sleeps.append,
        poll_interval=0.01,
    )

    joined = "\n".join(outputs).lower()
    assert "interrupted" in joined
