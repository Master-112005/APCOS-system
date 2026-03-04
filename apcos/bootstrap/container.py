"""Dependency wiring container for APCOS runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from apcos.bootstrap.config_loader import load_config
from core.behavior.calibration_engine import CalibrationEngine
from core.behavior.cpu_monitor import CPUMonitor
from core.behavior.memory_monitor import MemoryMonitor
from core.behavior.power_state_manager import PowerStateManager
from core.behavior.resource_governor import ResourceGovernor
from core.behavior.thread_limiter import ThreadLimiter
from core.cognition.challenge_logic import ChallengeLogic
from core.cognition.command_router import CommandRouter, LifecycleManager, TaskStore
from core.cognition.explanation_engine import ExplanationEngine
from core.cognition.intent_parser import parse_intent
from core.cognition.proactive_controller import ProactiveController
from core.cognition.reasoning_engine import ReasoningEngine
from core.identity.access_control import AccessControl
from core.identity.identity_resolver import IdentityResolver
from interface.interaction_controller import InteractionController
from services.hardware.battery_monitor import BatteryMonitor
from services.hardware.capability_detector import CapabilityDetector
from services.hardware.device_state_manager import DeviceStateManager
from services.hardware.microphone_health import MicrophoneHealth
from services.hardware.sleep_manager import SleepManager
from services.hardware.thermal_monitor import ThermalMonitor
from voice.asr_engine_real import ASREngine
from voice.audio_stream import AudioStream
from voice.model_manager import ModelManager
from voice.transcription_worker import TranscriptionWorker
from voice.voice_identity_stub import resolve_voice_identity
from voice.voice_session import RealVoiceSession, VoiceSession
from voice.wake_word import WakeWordDetector
from voice.wake_word_engine import WakeWordEngine


@dataclass
class AppContainer:
    """Constructed dependency graph for APCOS runtime."""

    config: Mapping[str, Any]
    config_path: str | Path

    def __post_init__(self) -> None:
        proactive_cfg = self._get_mapping(self.config.get("proactive", {}))
        confidence_threshold = float(proactive_cfg.get("confidence_threshold", 0.7))
        daily_limit = int(proactive_cfg.get("daily_limit", 3))

        self.lifecycle = LifecycleManager()
        self.task_store = TaskStore(lifecycle_manager=self.lifecycle)
        self.challenge_logic = ChallengeLogic()
        self.command_router = CommandRouter(
            task_store=self.task_store,
            lifecycle_manager=self.lifecycle,
            challenge_logic=self.challenge_logic,
            config_path=self.config_path,
        )
        self.calibration_engine = CalibrationEngine(config_path=self.config_path)
        self.proactive_controller = ProactiveController(
            confidence_threshold=confidence_threshold,
            daily_limit=daily_limit,
            calibration_engine=self.calibration_engine,
        )
        self.explanation_engine = ExplanationEngine()
        self.reasoning_engine = ReasoningEngine()
        self.identity_resolver = IdentityResolver()
        self.access_control = AccessControl()
        self.interaction_controller = InteractionController(
            parser=parse_intent,
            router=self.command_router,
            proactive_controller=self.proactive_controller,
            explanation_engine=self.explanation_engine,
            reasoning_engine=self.reasoning_engine,
            identity_resolver=self.identity_resolver,
            access_control=self.access_control,
        )

    @property
    def controller(self) -> InteractionController:
        """Return the wired interaction controller."""
        return self.interaction_controller

    @staticmethod
    def _get_mapping(value: Any) -> Mapping[str, Any]:
        if isinstance(value, Mapping):
            return value
        return {}


def build_app(
    config_path: str | Path = "configs/default.yaml",
    *,
    config: Mapping[str, Any] | None = None,
) -> InteractionController:
    """Build and return the APCOS interaction controller."""
    loaded_config = config if config is not None else load_config(config_path)
    container = AppContainer(config=loaded_config, config_path=config_path)
    return container.controller


def build_voice_session(
    config_path: str | Path = "configs/default.yaml",
    *,
    config: Mapping[str, Any] | None = None,
    wake_word_detector: WakeWordDetector | None = None,
) -> VoiceSession:
    """Build and return voice session runtime wiring."""
    controller = build_app(config_path, config=config)
    detector = wake_word_detector or WakeWordDetector()
    return VoiceSession(
        wake_word_detector=detector,
        interaction_controller=controller,
        voice_identity_resolver=resolve_voice_identity,
    )


def build_real_voice_session(
    config_path: str | Path = "configs/default.yaml",
    *,
    config: Mapping[str, Any] | None = None,
    audio_stream: AudioStream | None = None,
    wake_word_engine: WakeWordEngine | None = None,
    model_manager: ModelManager | None = None,
    asr_engine: ASREngine | None = None,
    transcription_worker: TranscriptionWorker | None = None,
    thread_limiter: ThreadLimiter | None = None,
    power_manager: PowerStateManager | None = None,
    resource_governor: ResourceGovernor | None = None,
    runtime_governor_enabled: bool = True,
) -> RealVoiceSession:
    """Build and return Stage 7 real voice runtime wiring."""
    loaded_config = config if config is not None else load_config(config_path)
    controller = build_app(config_path, config=loaded_config)
    runtime_cfg = AppContainer._get_mapping(loaded_config.get("runtime", {}))
    hardware_cfg = AppContainer._get_mapping(loaded_config.get("hardware", {}))

    cpu_threshold = float(runtime_cfg.get("cpu_threshold_percent", 75.0))
    memory_threshold_mb = float(runtime_cfg.get("memory_threshold_mb", 500.0))
    max_threads = int(runtime_cfg.get("max_threads", 4))
    initial_power_mode = str(runtime_cfg.get("power_mode", "NORMAL"))
    model_downgrade_enabled = bool(runtime_cfg.get("model_downgrade_enabled", True))
    idle_unload_seconds = float(runtime_cfg.get("idle_unload_seconds", 300.0))
    battery_low_percent = float(hardware_cfg.get("battery_low_percent", 20.0))
    battery_critical_percent = float(hardware_cfg.get("battery_critical_percent", 10.0))
    thermal_limit_celsius = float(hardware_cfg.get("thermal_limit_celsius", 75.0))

    stream = audio_stream or AudioStream()
    wake_engine = wake_word_engine or WakeWordEngine(audio_stream=stream)
    manager = model_manager or ModelManager()
    engine = asr_engine or ASREngine(model_manager=manager)
    limiter = thread_limiter or ThreadLimiter(max_threads=max_threads)
    worker = transcription_worker or TranscriptionWorker(
        asr_engine=engine,
        thread_limiter=limiter,
    )
    _ = CapabilityDetector().detect()

    sleep_manager = SleepManager(
        wake_engine=wake_engine,
        transcription_worker=worker,
        model_manager=manager,
    )
    device_state_manager = DeviceStateManager(
        battery_monitor=BatteryMonitor(
            low_percent=battery_low_percent,
            critical_percent=battery_critical_percent,
        ),
        thermal_monitor=ThermalMonitor(limit_celsius=thermal_limit_celsius),
        sleep_manager=sleep_manager,
        microphone_health=MicrophoneHealth(health_probe=stream.is_running),
    )

    governor = resource_governor
    if runtime_governor_enabled:
        governor = governor or ResourceGovernor(
            cpu_monitor=CPUMonitor(threshold_percent=cpu_threshold),
            memory_monitor=MemoryMonitor(threshold_mb=memory_threshold_mb),
            model_downgrade_enabled=model_downgrade_enabled,
            idle_unload_seconds=idle_unload_seconds,
        )
        governor.register_model_manager(manager)
        governor.register_thread_pool(limiter)
        governor.register_power_manager(power_manager or PowerStateManager(initial_mode=initial_power_mode))
        governor.register_asr_engine(engine)
        device_state_manager.register_runtime_governor(governor)

    return RealVoiceSession(
        wake_word_engine=wake_engine,
        audio_stream=stream,
        transcription_worker=worker,
        interaction_controller=controller,
        voice_identity_resolver=resolve_voice_identity,
        idle_unload_seconds=idle_unload_seconds,
        resource_governor=governor,
        device_state_manager=device_state_manager,
    )
