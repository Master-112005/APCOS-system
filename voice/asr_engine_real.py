"""Real ASR engine wrapper with timeout-safe transcription behavior."""

from __future__ import annotations

import re
from threading import Thread
from typing import Any

from voice.model_manager import ModelManager


class ASREngine:
    """Transcribe audio with managed model lifecycle and timeout protection."""

    def __init__(
        self,
        *,
        model_manager: ModelManager | None = None,
        timeout_seconds: float = 2.0,
    ) -> None:
        self._model_manager = model_manager or ModelManager()
        self._timeout_seconds = max(0.05, float(timeout_seconds))

    def transcribe(self, audio_bytes: bytes) -> str:
        """Return clean transcription text or empty string on failure/timeout."""
        if not audio_bytes:
            return ""

        model = self._model_manager.get_model()
        result: dict[str, Any] = {"text": ""}

        def _do_transcribe() -> None:
            self._model_manager.mark_transcription_start()
            try:
                result["text"] = self._transcribe_with_model(model, audio_bytes)
            except Exception:
                result["text"] = ""
            finally:
                self._model_manager.mark_transcription_end()

        worker = Thread(target=_do_transcribe, name="asr-transcribe-worker", daemon=True)
        worker.start()
        worker.join(timeout=self._timeout_seconds)
        if worker.is_alive():
            return ""

        return self._normalize_text(str(result.get("text", "")))

    def unload_if_idle(self, idle_seconds: float, *, force: bool = False) -> bool:
        """Delegate idle-unload behavior to model manager."""
        return self._model_manager.unload_if_idle(idle_seconds, force=force)

    def set_timeout(self, timeout_seconds: float) -> None:
        """Update transcription timeout bound."""
        self._timeout_seconds = max(0.05, float(timeout_seconds))

    @property
    def timeout_seconds(self) -> float:
        """Current transcription timeout configuration."""
        return self._timeout_seconds

    @property
    def model_manager(self) -> ModelManager:
        """Expose model manager for observability and tests."""
        return self._model_manager

    @staticmethod
    def _transcribe_with_model(model: Any, audio_bytes: bytes) -> str:
        if hasattr(model, "transcribe_bytes"):
            return str(model.transcribe_bytes(audio_bytes))
        if hasattr(model, "transcribe"):
            output = model.transcribe(audio_bytes)
            if isinstance(output, dict):
                return str(output.get("text", ""))
            return str(output)
        if callable(model):
            return str(model(audio_bytes))
        return ""

    @staticmethod
    def _normalize_text(text: str) -> str:
        cleaned = re.sub(r"[\x00-\x1f\x7f]+", " ", text).strip()
        return " ".join(cleaned.split())
