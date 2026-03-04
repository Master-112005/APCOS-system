"""Thread-safe ASR model lifecycle manager for on-device voice runtime."""

from __future__ import annotations

import inspect
import logging
import os
from threading import Lock
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

MODEL_SMALL = "SMALL"
MODEL_TINY = "TINY"


class _FallbackASRModel:
    """Deterministic fallback ASR model used when external backends are absent."""

    backend_name = "stub"

    def __init__(self, *, model_size: str) -> None:
        self.model_size = model_size
        self.estimated_bytes = 32 if model_size == MODEL_SMALL else 16

    def transcribe_bytes(self, audio_bytes: bytes) -> str:
        if not audio_bytes:
            return ""
        marker = b"text:"
        start = audio_bytes.find(marker)
        if start < 0:
            return ""
        payload = audio_bytes[start + len(marker) :]
        return payload.decode("utf-8", errors="ignore").strip()


def _default_model_loader(model_size: str = MODEL_SMALL) -> Any:
    """
    Load available ASR backend or fallback stub.

    Stage 7/8 keeps this dependency-safe: if real backends are unavailable, we
    return deterministic fallback without failing runtime startup.
    """
    backend = os.getenv("APCOS_REAL_ASR_BACKEND", "stub").lower().strip()
    if backend in {"stub", ""}:
        return _FallbackASRModel(model_size=model_size)

    # Optional placeholders for future real backends; currently fallback-safe.
    return _FallbackASRModel(model_size=model_size)


class ModelManager:
    """Lazy, thread-safe lifecycle manager for ASR model objects."""

    def __init__(self, *, model_loader: Callable[..., Any] | None = None) -> None:
        self._model_loader = model_loader or _default_model_loader
        self._model_lock = Lock()
        self._model: Any | None = None
        self._load_count = 0
        self._estimated_model_bytes = 0
        self._last_used_at = 0.0
        self._model_size = MODEL_SMALL
        self._active_transcriptions = 0

    def load_asr_model(self) -> Any:
        """Load model lazily once; return existing instance for repeated calls."""
        with self._model_lock:
            if self._model is None:
                model = self._call_loader(self._model_size)
                self._model = model
                self._load_count += 1
                self._estimated_model_bytes = self._estimate_model_size(model)
                logger.info(
                    "ASR model loaded backend=%s size=%s estimated_bytes=%s load_count=%s",
                    getattr(model, "backend_name", model.__class__.__name__),
                    self._model_size,
                    self._estimated_model_bytes,
                    self._load_count,
                )
            self._last_used_at = time.monotonic()
            return self._model

    def unload_asr_model(self) -> None:
        """Unload model reference to release memory."""
        with self._model_lock:
            if self._model is not None:
                logger.info("ASR model unloaded.")
            self._model = None
            self._estimated_model_bytes = 0

    def get_model(self) -> Any:
        """Return loaded model, lazily loading on first call."""
        return self.load_asr_model()

    def is_loaded(self) -> bool:
        """Return whether a model instance is currently loaded."""
        with self._model_lock:
            return self._model is not None

    def mark_transcription_start(self) -> None:
        """Mark an active transcription region."""
        with self._model_lock:
            self._active_transcriptions += 1
            self._last_used_at = time.monotonic()

    def mark_transcription_end(self) -> None:
        """Mark transcription completion."""
        with self._model_lock:
            if self._active_transcriptions > 0:
                self._active_transcriptions -= 1
            self._last_used_at = time.monotonic()

    def unload_if_idle(self, idle_seconds: float, *, force: bool = False) -> bool:
        """
        Unload model when idle threshold is exceeded.

        `force=True` ignores idle timeout but still respects active transcription
        protection.
        """
        if idle_seconds <= 0 and not force:
            return False

        with self._model_lock:
            if self._model is None:
                return False
            if self._active_transcriptions > 0:
                return False
            if not force:
                idle_for = time.monotonic() - self._last_used_at
                if idle_for < idle_seconds:
                    return False
            self._model = None
            self._estimated_model_bytes = 0
            logger.info("ASR model unloaded (force=%s).", force)
            return True

    def downgrade_model(self) -> bool:
        """Downgrade model size level if possible."""
        with self._model_lock:
            if self._model_size == MODEL_TINY:
                return False
            self._model_size = MODEL_TINY
            self._model = None
            self._estimated_model_bytes = 0
            logger.info("ASR model downgraded to size=%s", self._model_size)
            return True

    def upgrade_model(self) -> bool:
        """Upgrade model size level if possible."""
        with self._model_lock:
            if self._model_size == MODEL_SMALL:
                return False
            self._model_size = MODEL_SMALL
            self._model = None
            self._estimated_model_bytes = 0
            logger.info("ASR model upgraded to size=%s", self._model_size)
            return True

    @property
    def current_model_size(self) -> str:
        """Return active target model size."""
        with self._model_lock:
            return self._model_size

    @property
    def load_count(self) -> int:
        """Number of successful model load operations."""
        with self._model_lock:
            return self._load_count

    @property
    def estimated_model_bytes(self) -> int:
        """Approximate in-memory model size (best effort)."""
        with self._model_lock:
            return self._estimated_model_bytes

    def _call_loader(self, model_size: str) -> Any:
        try:
            signature = inspect.signature(self._model_loader)
            if len(signature.parameters) >= 1:
                return self._model_loader(model_size)
            return self._model_loader()
        except Exception:
            return self._model_loader()

    @staticmethod
    def _estimate_model_size(model: Any) -> int:
        try:
            return int(getattr(model, "estimated_bytes"))
        except Exception:
            try:
                return int(model.__sizeof__())
            except Exception:
                return 0
