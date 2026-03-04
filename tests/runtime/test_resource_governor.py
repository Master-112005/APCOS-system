from __future__ import annotations

from core.behavior.cpu_monitor import CPUMonitor
from core.behavior.memory_monitor import MemoryMonitor
from core.behavior.power_state_manager import PowerStateManager
from core.behavior.resource_governor import ResourceGovernor
from core.behavior.thread_limiter import ThreadLimiter
from voice.asr_engine_real import ASREngine
from voice.model_manager import MODEL_SMALL, MODEL_TINY, ModelManager


def test_resource_governor_downgrades_model_under_pressure() -> None:
    cpu = CPUMonitor(threshold_percent=75.0, sampler=lambda: 90.0)
    memory = MemoryMonitor(threshold_mb=500.0, reader=lambda: 100.0)
    governor = ResourceGovernor(cpu_monitor=cpu, memory_monitor=memory, idle_unload_seconds=9999.0)
    manager = ModelManager()
    manager.load_asr_model()

    governor.register_model_manager(manager)
    governor.register_thread_pool(ThreadLimiter(max_threads=4))
    governor.register_power_manager(PowerStateManager())

    event = governor.evaluate()
    assert "MODEL_DOWNGRADED" in event["actions"]
    assert manager.current_model_size == MODEL_TINY
    assert event["power_mode"] in {"LOW_POWER", "CRITICAL"}


def test_resource_governor_unloads_model_under_extreme_pressure() -> None:
    cpu = CPUMonitor(threshold_percent=75.0, sampler=lambda: 95.0)
    memory = MemoryMonitor(threshold_mb=500.0, reader=lambda: 700.0)
    governor = ResourceGovernor(cpu_monitor=cpu, memory_monitor=memory, idle_unload_seconds=9999.0)
    manager = ModelManager()
    manager.load_asr_model()

    governor.register_model_manager(manager)
    governor.register_power_manager(PowerStateManager())

    event = governor.evaluate()
    assert "MODEL_UNLOADED_FORCE" in event["actions"]
    assert manager.is_loaded() is False


def test_resource_governor_reduces_timeout_for_tiny_model_under_pressure() -> None:
    cpu = CPUMonitor(threshold_percent=75.0, sampler=lambda: 90.0)
    memory = MemoryMonitor(threshold_mb=500.0, reader=lambda: 100.0)
    governor = ResourceGovernor(cpu_monitor=cpu, memory_monitor=memory, idle_unload_seconds=9999.0)
    manager = ModelManager()
    manager.downgrade_model()
    engine = ASREngine(model_manager=manager, timeout_seconds=2.0)

    governor.register_model_manager(manager)
    governor.register_power_manager(PowerStateManager())
    governor.register_asr_engine(engine)

    event = governor.evaluate()
    assert "ASR_TIMEOUT_REDUCED" in event["actions"]
    assert engine.timeout_seconds <= 0.5
