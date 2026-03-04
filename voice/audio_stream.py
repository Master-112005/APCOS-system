"""Thread-safe audio stream abstraction for real voice pipeline."""

from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Callable


AudioSourceFn = Callable[[int], bytes]


class AudioStream:
    """Fixed-buffer audio stream with overflow/backpressure protection."""

    def __init__(
        self,
        *,
        chunk_size: int = 3200,
        max_buffer_chunks: int = 32,
        source: AudioSourceFn | None = None,
    ) -> None:
        if chunk_size < 1:
            raise ValueError("chunk_size must be >= 1")
        if max_buffer_chunks < 1:
            raise ValueError("max_buffer_chunks must be >= 1")

        self._chunk_size = int(chunk_size)
        self._source = source
        self._buffer = deque(maxlen=max_buffer_chunks)
        self._running = False
        self._dropped_chunks = 0
        self._lock = Lock()

    def start(self) -> None:
        """Start stream lifecycle."""
        with self._lock:
            self._running = True

    def stop(self) -> None:
        """Stop stream lifecycle and clear pending chunks."""
        with self._lock:
            self._running = False
            self._buffer.clear()

    def is_running(self) -> bool:
        """Return whether stream is active."""
        with self._lock:
            return self._running

    def push_chunk(self, chunk: bytes) -> None:
        """Push chunk into stream buffer with overflow dropping oldest entry."""
        if not chunk:
            return
        with self._lock:
            if not self._running:
                return
            if len(self._buffer) == self._buffer.maxlen:
                self._buffer.popleft()
                self._dropped_chunks += 1
            self._buffer.append(bytes(chunk[: self._chunk_size]))

    def read_chunk(self) -> bytes:
        """
        Read next audio chunk (non-blocking).

        Returns empty bytes when stream is stopped or no chunk is available.
        """
        with self._lock:
            if not self._running:
                return b""
            if self._buffer:
                return self._buffer.popleft()

        if self._source is None:
            return b""

        try:
            chunk = self._source(self._chunk_size)
        except Exception:
            return b""
        if not isinstance(chunk, (bytes, bytearray)):
            return b""
        return bytes(chunk[: self._chunk_size])

    @property
    def dropped_chunks(self) -> int:
        """Return number of dropped chunks due to buffer overflow."""
        with self._lock:
            return self._dropped_chunks
