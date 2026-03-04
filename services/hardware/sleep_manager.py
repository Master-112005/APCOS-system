"""Sleep/wake runtime control for APCOS hardware abstraction layer."""

from __future__ import annotations

from threading import Lock
from typing import Any


class SleepManager:
    """Pause/resume voice runtime components without touching cognitive state."""

    def __init__(
        self,
        *,
        wake_engine: Any | None = None,
        transcription_worker: Any | None = None,
        model_manager: Any | None = None,
    ) -> None:
        self._wake_engine = wake_engine
        self._transcription_worker = transcription_worker
        self._model_manager = model_manager
        self._sleeping = False
        self._lock = Lock()

    def enter_sleep(self) -> bool:
        """Enter sleep mode and pause runtime components."""
        with self._lock:
            if self._sleeping:
                return False
            if self._wake_engine is not None and hasattr(self._wake_engine, "stop"):
                self._wake_engine.stop()
            if self._transcription_worker is not None and hasattr(self._transcription_worker, "stop"):
                self._transcription_worker.stop()
            if self._model_manager is not None and hasattr(self._model_manager, "unload_if_idle"):
                try:
                    self._model_manager.unload_if_idle(0.0, force=True)
                except TypeError:
                    self._model_manager.unload_if_idle(0.0)
            self._sleeping = True
            return True

    def wake(self) -> bool:
        """Leave sleep mode and resume runtime components."""
        with self._lock:
            if not self._sleeping:
                return False

            worker_ready = True
            if self._transcription_worker is not None and hasattr(self._transcription_worker, "start"):
                started = self._transcription_worker.start()
                worker_ready = bool(True if started is None else started)

            if not worker_ready:
                return False

            if self._wake_engine is not None and hasattr(self._wake_engine, "start"):
                self._wake_engine.start()
            self._sleeping = False
            return True

    def is_sleeping(self) -> bool:
        """Return whether runtime is currently sleeping."""
        with self._lock:
            return self._sleeping

