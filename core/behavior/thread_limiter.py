"""Thread slot limiter for APCOS runtime components."""

from __future__ import annotations

from threading import BoundedSemaphore, Lock


class ThreadLimiter:
    """Semaphore-backed limiter for bounded worker thread creation."""

    def __init__(self, *, max_threads: int = 4) -> None:
        if max_threads < 1:
            raise ValueError("max_threads must be >= 1")
        self._max_threads = int(max_threads)
        self._semaphore = BoundedSemaphore(value=self._max_threads)
        self._lock = Lock()
        self._in_use = 0

    def acquire_slot(self, *, timeout: float = 0.01) -> bool:
        """Acquire a thread slot with bounded wait time."""
        acquired = self._semaphore.acquire(timeout=max(0.0, float(timeout)))
        if not acquired:
            return False
        with self._lock:
            self._in_use += 1
        return True

    def release_slot(self) -> None:
        """Release a previously acquired slot."""
        with self._lock:
            if self._in_use < 1:
                return
            self._in_use -= 1
        self._semaphore.release()

    def available_slots(self) -> int:
        """Return best-effort count of currently available thread slots."""
        with self._lock:
            return max(0, self._max_threads - self._in_use)

    @property
    def max_threads(self) -> int:
        """Configured maximum concurrent thread slots."""
        return self._max_threads
