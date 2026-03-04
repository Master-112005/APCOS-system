"""ASR transcription boundary for APCOS voice interaction (stub)."""

from __future__ import annotations

from threading import Lock
import time
from typing import Any, Callable


ModelLoader = Callable[[], Any]
PipelineBuilder = Callable[[Any], Any]


class ASREngine:
    """
    Lightweight ASR stub with deterministic profiling hooks.

    This implementation keeps stage behavior unchanged while providing:
    - lazy one-time model/pipeline initialization
    - thread-safe cache reuse
    - monotonic latency profiling metrics
    """

    def __init__(
        self,
        *,
        model_loader: ModelLoader | None = None,
        pipeline_builder: PipelineBuilder | None = None,
    ) -> None:
        self._model_loader = model_loader or (lambda: {"name": "stub-asr-model"})
        self._pipeline_builder = pipeline_builder or (lambda model: {"model": model})
        self._lock = Lock()
        self._cached_model: Any | None = None
        self._cached_pipeline: Any | None = None
        self._model_load_count = 0
        self._pipeline_build_count = 0
        self._call_sequence = 0
        self._last_profile: dict[str, Any] = {
            "sequence": 0,
            "cold_start": False,
            "cache_reused": False,
            "init_latency_ms": 0.0,
            "transcribe_latency_ms": 0.0,
            "total_latency_ms": 0.0,
            "model_load_count": 0,
            "pipeline_build_count": 0,
        }

    def transcribe(self, audio: bytes) -> str:
        """
        Deterministically transcribe audio payloads containing `text:`.

        Behavior is intentionally unchanged from the original stub:
        - payloads containing `text:` decode everything after the marker
        - empty/invalid payloads return empty transcript
        """
        start = time.perf_counter()
        init_latency_ms, cold_start = self._ensure_initialized()
        content_start = time.perf_counter()

        transcript = self._decode_payload(audio)

        transcribe_latency_ms = (time.perf_counter() - content_start) * 1000.0
        total_latency_ms = (time.perf_counter() - start) * 1000.0
        self._call_sequence += 1
        self._last_profile = {
            "sequence": self._call_sequence,
            "cold_start": cold_start,
            "cache_reused": not cold_start,
            "init_latency_ms": init_latency_ms,
            "transcribe_latency_ms": transcribe_latency_ms,
            "total_latency_ms": total_latency_ms,
            "model_load_count": self._model_load_count,
            "pipeline_build_count": self._pipeline_build_count,
        }
        return transcript

    def profile_snapshot(self) -> dict[str, Any]:
        """Return immutable snapshot of latest latency and cache metrics."""
        return dict(self._last_profile)

    def _ensure_initialized(self) -> tuple[float, bool]:
        start = time.perf_counter()
        cold_start = False
        with self._lock:
            if self._cached_model is None:
                self._cached_model = self._model_loader()
                self._model_load_count += 1
                cold_start = True
            if self._cached_pipeline is None:
                self._cached_pipeline = self._pipeline_builder(self._cached_model)
                self._pipeline_build_count += 1
                cold_start = True

            # Deterministic one-time warmup to make cold start measurable.
            if cold_start:
                _ = sum(index * index for index in range(20_000))

        return ((time.perf_counter() - start) * 1000.0, cold_start)

    @staticmethod
    def _decode_payload(audio: bytes) -> str:
        if not audio:
            return ""
        marker = b"text:"
        index = audio.find(marker)
        if index < 0:
            return ""
        raw = audio[index + len(marker) :]
        return raw.decode("utf-8", errors="ignore").strip()


_DEFAULT_ASR_ENGINE = ASREngine()


def transcribe(audio: bytes) -> str:
    """Backwards-compatible module-level transcription entrypoint."""
    return _DEFAULT_ASR_ENGINE.transcribe(audio)
