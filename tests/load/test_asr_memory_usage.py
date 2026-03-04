from __future__ import annotations

import os

from voice.asr_engine_real import ASREngine
from voice.model_manager import ModelManager


def test_asr_model_loads_once_and_memory_stays_bounded() -> None:
    manager = ModelManager()
    engine = ASREngine(model_manager=manager, timeout_seconds=0.2)
    max_bytes = int(os.getenv("APCOS_ASR_MODEL_MAX_BYTES", "500000000"))

    for _ in range(1000):
        text = engine.transcribe(b"tier:owner;text:Schedule review tomorrow at 9")
        assert isinstance(text, str)

    assert manager.load_count == 1
    assert manager.is_loaded() is True
    assert manager.estimated_model_bytes >= 0
    assert manager.estimated_model_bytes <= max_bytes


def test_model_unloads_after_idle_timeout() -> None:
    manager = ModelManager()
    engine = ASREngine(model_manager=manager, timeout_seconds=0.2)

    _ = engine.transcribe(b"text:Schedule standup tomorrow at 10")
    assert manager.is_loaded() is True

    unloaded = engine.unload_if_idle(0.0)
    # zero idle threshold is treated as disabled for safety.
    assert unloaded is False

    unloaded = engine.unload_if_idle(0.01)
    # may be true or false immediately depending on execution timing.
    if not unloaded:
        import time

        time.sleep(0.02)
        unloaded = engine.unload_if_idle(0.01)
    assert unloaded is True
    assert manager.is_loaded() is False
