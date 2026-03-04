"""TTS synthesis boundary with deterministic latency profiling hooks."""

from __future__ import annotations

from threading import Lock
import time
from typing import Any, Callable

PipelineLoader = Callable[[], Any]


class TTSEngine:
    """
    Lightweight TTS stub with lazy pipeline cache and profiling metrics.

    This module keeps synthesis deterministic and non-blocking while enabling
    warmup/cached latency measurement.
    """

    def __init__(
        self,
        *,
        pipeline_loader: PipelineLoader | None = None,
    ) -> None:
        self._pipeline_loader = pipeline_loader or (lambda: {"name": "stub-tts-pipeline"})
        self._lock = Lock()
        self._cached_pipeline: Any | None = None
        self._pipeline_load_count = 0
        self._call_sequence = 0
        self._last_profile: dict[str, Any] = {
            "sequence": 0,
            "cold_start": False,
            "cache_reused": False,
            "startup_latency_ms": 0.0,
            "playback_latency_ms": 0.0,
            "total_latency_ms": 0.0,
            "pipeline_load_count": 0,
        }

    def synthesize(self, text: str) -> bytes:
        """Return deterministic audio bytes for input text."""
        start = time.perf_counter()
        startup_latency_ms, cold_start = self._ensure_initialized()
        playback_start = time.perf_counter()

        audio = str(text).encode("utf-8")

        playback_latency_ms = (time.perf_counter() - playback_start) * 1000.0
        total_latency_ms = (time.perf_counter() - start) * 1000.0
        self._call_sequence += 1
        self._last_profile = {
            "sequence": self._call_sequence,
            "cold_start": cold_start,
            "cache_reused": not cold_start,
            "startup_latency_ms": startup_latency_ms,
            "playback_latency_ms": playback_latency_ms,
            "total_latency_ms": total_latency_ms,
            "pipeline_load_count": self._pipeline_load_count,
        }
        return audio

    def profile_snapshot(self) -> dict[str, Any]:
        """Return immutable snapshot of latest TTS latency metrics."""
        return dict(self._last_profile)

    def _ensure_initialized(self) -> tuple[float, bool]:
        start = time.perf_counter()
        cold_start = False
        with self._lock:
            if self._cached_pipeline is None:
                self._cached_pipeline = self._pipeline_loader()
                self._pipeline_load_count += 1
                cold_start = True
                # Deterministic one-time warmup to model startup overhead.
                _ = sum(index * index for index in range(20_000))
        return ((time.perf_counter() - start) * 1000.0, cold_start)


_DEFAULT_TTS_ENGINE = TTSEngine()


def synthesize(text: str) -> bytes:
    """Backwards-compatible module-level TTS entrypoint."""
    return _DEFAULT_TTS_ENGINE.synthesize(text)
