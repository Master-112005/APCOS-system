"""Threaded wake-word engine for real voice pipeline."""

from __future__ import annotations

import re
from threading import Event, Lock, Thread
import time

from voice.audio_stream import AudioStream


class WakeWordEngine:
    """Dedicated wake-word listener thread emitting wake events only."""

    def __init__(
        self,
        *,
        audio_stream: AudioStream,
        trigger_phrase: str = "hey apcos",
        poll_interval: float = 0.02,
    ) -> None:
        normalized = " ".join(trigger_phrase.lower().strip().split())
        if not normalized:
            raise ValueError("trigger_phrase must not be empty")
        self._audio_stream = audio_stream
        self._trigger_phrase = normalized
        self._poll_interval = max(0.005, float(poll_interval))
        self._wake_event = Event()
        self._stop_event = Event()
        self._thread_lock = Lock()
        self._thread: Thread | None = None

    def start(self) -> None:
        """Start wake detection thread once."""
        with self._thread_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = Thread(target=self._run_loop, name="wake-word-engine", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop wake detection thread and clear wake signal."""
        with self._thread_lock:
            self._stop_event.set()
            thread = self._thread
            self._thread = None
        if thread is not None:
            thread.join(timeout=1.0)
        self._wake_event.clear()

    def wait_for_wake(self, timeout: float = 0.0) -> bool:
        """Wait for wake event with timeout, then clear consumed signal."""
        triggered = self._wake_event.wait(timeout=max(0.0, float(timeout)))
        if triggered:
            self._wake_event.clear()
            return True
        return False

    def is_running(self) -> bool:
        """Return whether wake thread is currently active."""
        thread = self._thread
        return bool(thread is not None and thread.is_alive())

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            if self._wake_event.is_set():
                time.sleep(self._poll_interval)
                continue
            chunk = self._audio_stream.read_chunk()
            if self._detect_trigger(chunk):
                self._wake_event.set()
            time.sleep(self._poll_interval)

    def _detect_trigger(self, chunk: bytes) -> bool:
        if not chunk:
            return False
        text = chunk.decode("utf-8", errors="ignore").lower()
        normalized = re.sub(r"\s+", " ", text).strip()
        return self._trigger_phrase in normalized
