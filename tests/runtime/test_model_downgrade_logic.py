from __future__ import annotations

import threading
import time

from voice.model_manager import MODEL_SMALL, MODEL_TINY, ModelManager


def test_model_manager_downgrade_and_upgrade_cycle() -> None:
    manager = ModelManager()
    assert manager.current_model_size == MODEL_SMALL
    assert manager.downgrade_model() is True
    assert manager.current_model_size == MODEL_TINY
    assert manager.downgrade_model() is False
    assert manager.upgrade_model() is True
    assert manager.current_model_size == MODEL_SMALL


def test_model_load_once_under_concurrent_access() -> None:
    manager = ModelManager()

    def worker() -> None:
        for _ in range(20):
            manager.load_asr_model()

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert manager.load_count == 1


def test_force_unload_skips_when_transcription_active() -> None:
    manager = ModelManager()
    manager.load_asr_model()
    manager.mark_transcription_start()
    assert manager.unload_if_idle(0.0, force=True) is False
    manager.mark_transcription_end()
    assert manager.unload_if_idle(0.0, force=True) is True
