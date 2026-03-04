"""Dedicated ASR worker thread for non-blocking audio transcription."""

from __future__ import annotations

from threading import Event, Lock, Thread
from typing import Callable

from core.behavior.thread_limiter import ThreadLimiter
from voice.asr_engine_real import ASREngine
from voice.thread_safe_queue import ThreadSafeQueue


class TranscriptionWorker:
    """Queue-based ASR worker that never calls router or interaction logic."""

    def __init__(
        self,
        *,
        asr_engine: ASREngine,
        max_queue_size: int = 32,
        poll_interval: float = 0.02,
        thread_limiter: ThreadLimiter | None = None,
    ) -> None:
        self._asr_engine = asr_engine
        self._poll_interval = max(0.005, float(poll_interval))
        self._audio_queue: ThreadSafeQueue[bytes] = ThreadSafeQueue(max_size=max_queue_size)
        self._text_queue: ThreadSafeQueue[str] = ThreadSafeQueue(max_size=max_queue_size)
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._thread_lock = Lock()
        self._on_transcription: Callable[[str], None] | None = None
        self._thread_limiter = thread_limiter
        self._slot_acquired = False

    def set_on_transcription(self, callback: Callable[[str], None] | None) -> None:
        """Optional callback invoked on worker thread after transcription."""
        self._on_transcription = callback

    def start(self) -> bool:
        """Start worker thread once. Returns False if no thread slot is available."""
        with self._thread_lock:
            if self._thread is not None and self._thread.is_alive():
                return True
            if self._thread_limiter is not None:
                self._slot_acquired = self._thread_limiter.acquire_slot(timeout=self._poll_interval)
                if not self._slot_acquired:
                    return False
            self._stop_event.clear()
            self._thread = Thread(
                target=self._run_loop,
                name="asr-transcription-worker",
                daemon=True,
            )
            self._thread.start()
            return True

    def stop(self) -> None:
        """Stop worker thread and close internal queues."""
        with self._thread_lock:
            self._stop_event.set()
            self._audio_queue.close()
            self._text_queue.close()
            thread = self._thread
            self._thread = None
        if thread is not None:
            thread.join(timeout=1.0)
        if self._thread_limiter is not None and self._slot_acquired:
            self._thread_limiter.release_slot()
            self._slot_acquired = False

    def is_running(self) -> bool:
        """Return whether worker is active."""
        thread = self._thread
        return bool(thread is not None and thread.is_alive())

    def submit_audio(self, audio_bytes: bytes) -> bool:
        """Submit audio payload for transcription."""
        if not audio_bytes:
            return False
        return self._audio_queue.put(bytes(audio_bytes), timeout=self._poll_interval)

    def get_transcription(self, timeout: float = 0.1) -> str | None:
        """Fetch next transcription result from output queue."""
        return self._text_queue.get(timeout=max(0.001, float(timeout)))

    @property
    def asr_engine(self) -> ASREngine:
        """Expose ASR engine for observability/testing."""
        return self._asr_engine

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            audio = self._audio_queue.get(timeout=self._poll_interval)
            if audio is None:
                continue
            text = self._asr_engine.transcribe(audio)
            if not text:
                continue
            self._text_queue.put(text, timeout=self._poll_interval)
            callback = self._on_transcription
            if callback is not None:
                callback(text)
