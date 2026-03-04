from __future__ import annotations

from services.hardware.sleep_manager import SleepManager


class _FakeWakeEngine:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


class _FakeWorker:
    def __init__(self, start_result: bool = True) -> None:
        self.start_result = start_result
        self.started = False
        self.stopped = False

    def start(self) -> bool:
        self.started = True
        return self.start_result

    def stop(self) -> None:
        self.stopped = True


class _FakeModelManager:
    def __init__(self) -> None:
        self.unload_calls = 0

    def unload_if_idle(self, idle_seconds: float, force: bool = False) -> bool:
        _ = idle_seconds
        _ = force
        self.unload_calls += 1
        return True


def test_sleep_manager_pauses_and_resumes_runtime_components() -> None:
    wake = _FakeWakeEngine()
    worker = _FakeWorker(start_result=True)
    model = _FakeModelManager()
    manager = SleepManager(wake_engine=wake, transcription_worker=worker, model_manager=model)

    assert manager.enter_sleep() is True
    assert manager.is_sleeping() is True
    assert wake.stopped is True
    assert worker.stopped is True
    assert model.unload_calls == 1

    assert manager.wake() is True
    assert manager.is_sleeping() is False
    assert wake.started is True
    assert worker.started is True


def test_sleep_manager_stays_sleeping_when_worker_cannot_restart() -> None:
    manager = SleepManager(
        wake_engine=_FakeWakeEngine(),
        transcription_worker=_FakeWorker(start_result=False),
        model_manager=_FakeModelManager(),
    )
    assert manager.enter_sleep() is True
    assert manager.wake() is False
    assert manager.is_sleeping() is True

