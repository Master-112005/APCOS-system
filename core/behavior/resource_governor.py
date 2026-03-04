"""Runtime resource governor for voice pipeline protection."""

from __future__ import annotations

import logging
from threading import Event, Lock, Thread
import time
from typing import Any

from core.behavior.cpu_monitor import CPUMonitor
from core.behavior.memory_monitor import MemoryMonitor
from core.behavior.power_state_manager import PowerMode, PowerStateManager

logger = logging.getLogger(__name__)


class ResourceGovernor:
    """
    Coordinate runtime resource health decisions.

    The governor is mutation-neutral: it only controls runtime resource behavior
    (model lifecycle / thread pressure hints) and never touches router/memory.
    """

    def __init__(
        self,
        *,
        cpu_monitor: CPUMonitor,
        memory_monitor: MemoryMonitor,
        evaluation_interval_seconds: float = 1.0,
        model_downgrade_enabled: bool = True,
        idle_unload_seconds: float = 300.0,
    ) -> None:
        self._cpu_monitor = cpu_monitor
        self._memory_monitor = memory_monitor
        self._evaluation_interval = max(0.1, float(evaluation_interval_seconds))
        self._model_downgrade_enabled = bool(model_downgrade_enabled)
        self._idle_unload_seconds = max(1.0, float(idle_unload_seconds))

        self._model_manager: Any | None = None
        self._thread_limiter: Any | None = None
        self._power_manager: PowerStateManager | None = None
        self._asr_engine: Any | None = None
        self._default_asr_timeout: float | None = None
        self._evaluation_paused = False
        self._cpu_budget_scale = 1.0

        self._stop_event = Event()
        self._thread: Thread | None = None
        self._thread_lock = Lock()

    def register_model_manager(self, model_manager: Any) -> None:
        """Register model manager for pressure actions."""
        self._model_manager = model_manager

    def register_thread_pool(self, thread_limiter: Any) -> None:
        """Register thread limiter for slot pressure signals."""
        self._thread_limiter = thread_limiter

    def register_power_manager(self, power_manager: PowerStateManager) -> None:
        """Register power mode manager."""
        self._power_manager = power_manager

    def register_asr_engine(self, asr_engine: Any) -> None:
        """Register ASR engine for timeout control under sustained pressure."""
        self._asr_engine = asr_engine
        try:
            self._default_asr_timeout = float(asr_engine.timeout_seconds)
        except Exception:
            self._default_asr_timeout = None

    def pause_evaluation(self, *, reason: str = "") -> bool:
        """Pause periodic evaluate actions until resumed."""
        _ = reason
        if self._evaluation_paused:
            return False
        self._evaluation_paused = True
        return True

    def resume_evaluation(self, *, reason: str = "") -> bool:
        """Resume periodic evaluate actions."""
        _ = reason
        if not self._evaluation_paused:
            return False
        self._evaluation_paused = False
        return True

    def reduce_cpu_budget(self, *, reason: str = "", budget_scale: float = 0.5) -> bool:
        """Apply conservative runtime budget reduction hint."""
        _ = reason
        target = max(0.1, min(1.0, float(budget_scale)))
        if target >= self._cpu_budget_scale:
            return False
        self._cpu_budget_scale = target
        if self._asr_engine is not None and hasattr(self._asr_engine, "set_timeout"):
            current_timeout = float(getattr(self._asr_engine, "timeout_seconds", 2.0))
            self._asr_engine.set_timeout(min(current_timeout, 0.35))
        return True

    def force_model_downgrade(self, *, reason: str = "") -> bool:
        """Request model downgrade immediately if manager supports it."""
        _ = reason
        model_manager = self._model_manager
        if model_manager is None or not hasattr(model_manager, "downgrade_model"):
            return False
        try:
            return bool(model_manager.downgrade_model())
        except Exception:
            return False

    def force_model_unload(self, *, reason: str = "") -> bool:
        """Request forced model unload if currently safe."""
        _ = reason
        model_manager = self._model_manager
        if model_manager is None or not hasattr(model_manager, "unload_if_idle"):
            return False
        try:
            return bool(model_manager.unload_if_idle(0.0, force=True))
        except TypeError:
            try:
                return bool(model_manager.unload_if_idle(0.0))
            except Exception:
                return False
        except Exception:
            return False

    def evaluate(self) -> dict[str, Any]:
        """Evaluate runtime signals and emit structured governor decisions."""
        cpu_usage = self._cpu_monitor.current_usage()
        memory_usage_mb = self._memory_monitor.current_usage_mb()
        cpu_over = self._cpu_monitor.is_over_threshold()
        memory_high = self._memory_monitor.is_pressure_high()

        if self._power_manager is None:
            self._power_manager = PowerStateManager()
        mode = self._power_manager.update_mode(
            cpu_over_threshold=cpu_over,
            memory_pressure_high=memory_high,
        )

        actions: list[str] = []
        thread_slots = None
        if self._thread_limiter is not None and hasattr(self._thread_limiter, "available_slots"):
            try:
                thread_slots = int(self._thread_limiter.available_slots())
            except Exception:
                thread_slots = None

        model_manager = self._model_manager
        if self._evaluation_paused:
            actions.append("EVALUATION_PAUSED")
        elif model_manager is not None:
            if memory_high and cpu_over:
                unloaded = False
                if hasattr(model_manager, "unload_if_idle"):
                    try:
                        unloaded = bool(model_manager.unload_if_idle(0.0, force=True))
                    except TypeError:
                        unloaded = bool(model_manager.unload_if_idle(0.0))
                if unloaded:
                    actions.append("MODEL_UNLOADED_FORCE")
            elif self._model_downgrade_enabled and (cpu_over or memory_high):
                if hasattr(model_manager, "downgrade_model") and model_manager.downgrade_model():
                    actions.append("MODEL_DOWNGRADED")
            elif mode == PowerMode.NORMAL and hasattr(model_manager, "upgrade_model"):
                if model_manager.upgrade_model():
                    actions.append("MODEL_UPGRADED")

            if hasattr(model_manager, "unload_if_idle"):
                try:
                    if model_manager.unload_if_idle(self._idle_unload_seconds):
                        actions.append("MODEL_UNLOADED_IDLE")
                except Exception:
                    pass

            if self._asr_engine is not None and hasattr(model_manager, "current_model_size"):
                current_size = str(getattr(model_manager, "current_model_size", ""))
                if (cpu_over or memory_high) and current_size == "TINY":
                    if hasattr(self._asr_engine, "set_timeout"):
                        current_timeout = float(getattr(self._asr_engine, "timeout_seconds", 2.0))
                        reduced = min(current_timeout, 0.5)
                        self._asr_engine.set_timeout(reduced)
                        actions.append("ASR_TIMEOUT_REDUCED")
                elif mode == PowerMode.NORMAL and self._default_asr_timeout is not None:
                    if hasattr(self._asr_engine, "set_timeout"):
                        self._asr_engine.set_timeout(self._default_asr_timeout)
                        actions.append("ASR_TIMEOUT_RESTORED")

        event = {
            "timestamp": time.time(),
            "cpu_usage_percent": cpu_usage,
            "memory_usage_mb": memory_usage_mb,
            "cpu_over_threshold": cpu_over,
            "memory_pressure_high": memory_high,
            "power_mode": mode.value,
            "thread_slots_available": thread_slots,
            "evaluation_paused": self._evaluation_paused,
            "cpu_budget_scale": self._cpu_budget_scale,
            "actions": tuple(actions),
        }
        return event

    def start(self) -> None:
        """Start low-frequency evaluation loop in a single daemon thread."""
        with self._thread_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = Thread(target=self._run_loop, name="resource-governor", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop governor loop thread."""
        with self._thread_lock:
            self._stop_event.set()
            thread = self._thread
            self._thread = None
        if thread is not None:
            thread.join(timeout=1.0)

    def is_running(self) -> bool:
        """Return whether governor loop thread is alive."""
        thread = self._thread
        return bool(thread is not None and thread.is_alive())

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.evaluate()
            except Exception:
                logger.debug("Resource governor evaluate() failed.", exc_info=False)
            time.sleep(self._evaluation_interval)
