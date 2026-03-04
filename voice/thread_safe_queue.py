"""Thread-safe bounded queue utilities for voice pipeline handoff."""

from __future__ import annotations

from queue import Empty, Full, Queue
from threading import Event
from typing import Generic, TypeVar

T = TypeVar("T")


class ThreadSafeQueue(Generic[T]):
    """Bounded queue wrapper with close semantics for worker coordination."""

    def __init__(self, *, max_size: int = 32) -> None:
        if max_size < 1:
            raise ValueError("max_size must be >= 1")
        self._queue: Queue[T] = Queue(maxsize=max_size)
        self._closed = Event()

    def put(self, item: T, *, timeout: float = 0.01) -> bool:
        """Best-effort enqueue; returns False when queue is full or closed."""
        if self._closed.is_set():
            return False
        try:
            self._queue.put(item, timeout=timeout)
            return True
        except Full:
            return False

    def get(self, *, timeout: float = 0.01) -> T | None:
        """Best-effort dequeue; returns None when queue is empty or closed."""
        if self._closed.is_set() and self._queue.empty():
            return None
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            return None

    def close(self) -> None:
        """Mark queue closed and prevent new items from being added."""
        self._closed.set()

    def is_closed(self) -> bool:
        """Return whether close() has been called."""
        return self._closed.is_set()

    def size(self) -> int:
        """Return current queue size estimate."""
        return self._queue.qsize()
