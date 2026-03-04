"""Fixtures for extended runtime soak stability validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import io
import re
import threading
import time
import tracemalloc
from typing import Any

from core.cognition.proactive_controller import ProactiveController
from core.cognition.reasoning_engine import ReasoningEngine
from services.ipc.rust_bridge import RustBridge, build_energy_result
from services.sync_daemon import SyncDaemon
from voice.asr_engine import ASREngine
from voice.tts_engine import TTSEngine
from voice.voice_session import VoiceSession
from voice.wake_word import WakeWordDetector


MUTATION_OUTPUT_PATTERN = re.compile(
    r"\b(create_task\s*\(|archive\s*\(|update_task\s*\(|delete\s*\()",
    re.IGNORECASE,
)


@dataclass
class ExtendedEnergyState:
    """Deterministic battery model used in soak validation."""

    battery_percent: int = 60
    decisions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def mode(self) -> str:
        if self.battery_percent >= 50:
            return "STRATEGIC"
        if self.battery_percent >= 20:
            return "REDUCED"
        return "SILENT"

    def set_battery(self, value: int) -> None:
        self.battery_percent = max(0, min(100, int(value)))


class ImmediateSyncBridge:
    """Immediate envelope sink to track queue/backlog characteristics."""

    def __init__(self) -> None:
        self.processed_count = 0
        self.max_backlog = 0
        self._pending = 0
        self.invalid_messages = 0
        self.sample_messages: list[dict[str, Any]] = []

    def publish_event(self, message: dict[str, Any]) -> None:
        self._process(message)

    def send_message(self, message: dict[str, Any]) -> None:
        self._process(message)

    def _process(self, message: dict[str, Any]) -> None:
        self._pending += 1
        self.max_backlog = max(self.max_backlog, self._pending)

        msg_type = str(message.get("message_type", ""))
        payload = message.get("payload", {})
        if msg_type != "EVENT" or not isinstance(payload, dict):
            self.invalid_messages += 1
        else:
            if len(self.sample_messages) < 5:
                self.sample_messages.append(dict(message))

        self.processed_count += 1
        self._pending -= 1


class _ExtendedVoiceController:
    """Energy-gated voice controller for deterministic soak simulation."""

    def __init__(self, harness: "ExtendedRuntimeHarness") -> None:
        self._harness = harness
        self.identity: Any = None

    def set_identity(self, identity: Any) -> None:
        self.identity = identity

    def handle_input(self, user_text: str) -> str:
        text = (user_text or "").strip()
        if text.lower().startswith("/strategy"):
            result = self._harness.run_reasoning_cycle(query=text[9:].strip() or "strategy")
            if not result["allowed"]:
                return f"Energy gate: {result['reason']}"
            return f"Strategy: {result['summary']}"

        allowed, response, reason = self._harness.bridge.validate_energy_and_maybe_execute(
            battery_percent=self._harness.energy_state.battery_percent,
            execution_type="VOICE",
            correlation_id=f"voice-cycle-{self._harness.current_cycle_index}",
            execute_callable=lambda: "Voice command acknowledged.",
        )
        if not allowed:
            return f"Energy gate: {reason}"
        return str(response)


@dataclass(frozen=True)
class ExtendedRuntimeMetrics:
    """Aggregated soak-test metrics for 10k-cycle simulation."""

    requested_cycles: int
    completed_cycles: int
    total_elapsed_ms: float
    average_cycle_latency_ms: float
    max_cycle_latency_ms: float
    min_cycle_latency_ms: float
    latency_samples_ms: tuple[float, ...]
    memory_start_kb: float
    memory_mid_kb: float
    memory_end_kb: float
    thread_start_count: int
    thread_mid_count: int
    thread_end_count: int
    asr_model_load_count: int
    asr_pipeline_build_count: int
    tts_pipeline_load_count: int
    llm_allowed_count: int
    llm_denied_count: int
    llm_downgraded_count: int
    unsafe_reasoning_outputs: int
    proactive_executed_count: int
    proactive_suppressed_count: int
    proactive_suppressed_by_cooldown: int
    sync_event_count: int
    sync_processed_count: int
    sync_max_backlog: int
    sync_invalid_message_count: int
    voice_allowed_count: int
    voice_denied_count: int
    energy_transition_count: int
    energy_modes_seen: tuple[str, ...]


class ExtendedRuntimeHarness:
    """Deterministic always-on runtime simulation across 10k combined cycles."""

    ENERGY_SEQUENCE = (60, 30, 10, 5, 70)

    def __init__(self) -> None:
        self.energy_state = ExtendedEnergyState()
        self.bridge = RustBridge(
            in_stream=io.StringIO(""),
            out_stream=io.StringIO(),
            energy_transport=self._energy_transport,
        )
        self.reasoning_engine = ReasoningEngine()
        self.proactive_controller = ProactiveController(
            confidence_threshold=0.7,
            daily_limit=100_000,
            recent_suggestion_window=12,
            max_suggestions_per_window=3,
            repetition_cooldown_steps=4,
        )
        self.sync_bridge = ImmediateSyncBridge()
        self.sync_daemon = SyncDaemon(self.sync_bridge)
        self.asr = ASREngine()
        self.tts = TTSEngine()
        self.current_cycle_index = 0
        self._audio_payload = b"tier:owner;text:status check"
        self._voice_controller = _ExtendedVoiceController(self)
        self._voice_session = VoiceSession(
            wake_word_detector=WakeWordDetector(event_source=lambda: "hey apcos"),
            interaction_controller=self._voice_controller,
            audio_capture=self._capture_audio,
            asr_transcriber=self.asr.transcribe,
        )
        self.llm_allowed_count = 0
        self.llm_denied_count = 0
        self.llm_downgraded_count = 0
        self.unsafe_reasoning_outputs = 0
        self.proactive_executed_count = 0
        self.proactive_suppressed_count = 0
        self.proactive_suppressed_by_cooldown = 0
        self.sync_event_count = 0
        self.voice_allowed_count = 0
        self.voice_denied_count = 0
        self.energy_transition_count = 0
        self._base_time = datetime(2026, 2, 20, tzinfo=timezone.utc)

    def run(self, *, total_cycles: int) -> ExtendedRuntimeMetrics:
        if total_cycles <= 0:
            return self._empty_metrics()

        cycle_latencies: list[float] = []
        midpoint = total_cycles // 2
        thread_start = threading.active_count()
        thread_mid = thread_start
        tracemalloc.start()
        memory_start = self._memory_kb()
        memory_mid = memory_start

        soak_start = time.perf_counter()
        for index in range(total_cycles):
            self.current_cycle_index = index
            if index % 50 == 0:
                self._simulate_energy_transition(index)

            cycle_start = time.perf_counter()
            self._run_voice_cycle(index)
            self.run_reasoning_cycle(query=f"Plan cycle {index % 11}")
            self._run_sync_cycle(index)
            self._run_proactive_cycle(index)
            cycle_latencies.append((time.perf_counter() - cycle_start) * 1000.0)

            if index == (midpoint - 1):
                thread_mid = threading.active_count()
                memory_mid = self._memory_kb()

        total_elapsed_ms = (time.perf_counter() - soak_start) * 1000.0
        thread_end = threading.active_count()
        memory_end = self._memory_kb()
        tracemalloc.stop()

        asr_profile = self.asr.profile_snapshot()
        tts_profile = self.tts.profile_snapshot()
        modes_seen = tuple(
            sorted(
                {
                    str(item.get("mode", ""))
                    for item in self.energy_state.decisions
                    if isinstance(item, dict)
                }
            )
        )

        return ExtendedRuntimeMetrics(
            requested_cycles=total_cycles,
            completed_cycles=total_cycles,
            total_elapsed_ms=total_elapsed_ms,
            average_cycle_latency_ms=sum(cycle_latencies) / len(cycle_latencies),
            max_cycle_latency_ms=max(cycle_latencies),
            min_cycle_latency_ms=min(cycle_latencies),
            latency_samples_ms=tuple(cycle_latencies),
            memory_start_kb=memory_start,
            memory_mid_kb=memory_mid,
            memory_end_kb=memory_end,
            thread_start_count=thread_start,
            thread_mid_count=thread_mid,
            thread_end_count=thread_end,
            asr_model_load_count=int(asr_profile.get("model_load_count", 0)),
            asr_pipeline_build_count=int(asr_profile.get("pipeline_build_count", 0)),
            tts_pipeline_load_count=int(tts_profile.get("pipeline_load_count", 0)),
            llm_allowed_count=self.llm_allowed_count,
            llm_denied_count=self.llm_denied_count,
            llm_downgraded_count=self.llm_downgraded_count,
            unsafe_reasoning_outputs=self.unsafe_reasoning_outputs,
            proactive_executed_count=self.proactive_executed_count,
            proactive_suppressed_count=self.proactive_suppressed_count,
            proactive_suppressed_by_cooldown=self.proactive_suppressed_by_cooldown,
            sync_event_count=self.sync_event_count,
            sync_processed_count=self.sync_bridge.processed_count,
            sync_max_backlog=self.sync_bridge.max_backlog,
            sync_invalid_message_count=self.sync_bridge.invalid_messages,
            voice_allowed_count=self.voice_allowed_count,
            voice_denied_count=self.voice_denied_count,
            energy_transition_count=self.energy_transition_count,
            energy_modes_seen=modes_seen,
        )

    def run_reasoning_cycle(self, *, query: str) -> dict[str, Any]:
        validation = self.bridge.request_energy_validation(
            battery_percent=self.energy_state.battery_percent,
            execution_type="LLM",
            correlation_id=f"llm-cycle-{self.current_cycle_index}",
        )
        payload = dict(validation.get("payload", {}))
        allowed = bool(payload.get("allowed", False))
        if not allowed:
            self.llm_denied_count += 1
            reason = str(payload.get("reason", "ENERGY_DENIED"))
            return {"allowed": False, "summary": "", "downgraded": False, "reason": reason}

        self.llm_allowed_count += 1
        context: dict[str, Any] = {"goal": query, "horizon_days": 7}
        downgraded = False
        if self.energy_state.mode == "REDUCED":
            context = {"goal": query[:64], "horizon_days": 1, "low_energy": True}
            downgraded = True
            self.llm_downgraded_count += 1

        output = self.reasoning_engine.generate_strategy(context)
        summary = output.summary
        if MUTATION_OUTPUT_PATTERN.search(summary):
            self.unsafe_reasoning_outputs += 1

        return {
            "allowed": True,
            "summary": summary,
            "downgraded": downgraded,
            "reason": None,
        }

    def _run_voice_cycle(self, index: int) -> None:
        self._audio_payload = f"tier:owner;text:status check {index % 7}".encode("utf-8")
        response = str(self._voice_session.run_once() or "")
        self.tts.synthesize(response)
        if "voice command acknowledged" in response.lower():
            self.voice_allowed_count += 1
        else:
            self.voice_denied_count += 1

    def _run_sync_cycle(self, index: int) -> None:
        self.sync_daemon.receive_sync(
            {
                "source_id": f"runtime-source-{index % 5}",
                "sync_type": "TASK_UPDATE",
                "payload": {"external_task_id": f"ext-{index}", "sequence": index},
                "timestamp": int((self._base_time + timedelta(seconds=index)).timestamp()),
                "correlation_id": f"runtime-sync-{index}",
                "merge_hint": {
                    "source_priority": "normal",
                    "version": "v1",
                    "external_timestamp": int((self._base_time + timedelta(seconds=index)).timestamp()),
                },
            }
        )
        self.sync_event_count += 1

    def _run_proactive_cycle(self, index: int) -> None:
        context = {
            "overdue_tasks": 2 + (index % 2),
            "scheduled_tasks_today": 6,
            "daily_capacity": 5,
            "goal_alignment_score": 0.55,
        }
        allowed, suggestions, _ = self.bridge.validate_energy_and_maybe_execute(
            battery_percent=self.energy_state.battery_percent,
            execution_type="PROACTIVE",
            correlation_id=f"proactive-cycle-{index}",
            execute_callable=lambda: self.proactive_controller.evaluate(
                context,
                now=self._base_time + timedelta(seconds=index),
            ),
        )
        if not allowed:
            self.proactive_suppressed_count += 1
            return

        self.proactive_executed_count += 1
        if not list(suggestions or []):
            self.proactive_suppressed_by_cooldown += 1

    def _simulate_energy_transition(self, cycle_index: int) -> None:
        sequence_index = (cycle_index // 50) % len(self.ENERGY_SEQUENCE)
        self.energy_state.set_battery(self.ENERGY_SEQUENCE[sequence_index])
        self.energy_transition_count += 1

    def _capture_audio(self) -> bytes:
        return self._audio_payload

    def _energy_transport(self, request: dict[str, Any]) -> dict[str, Any]:
        correlation_id = str(request.get("correlation_id", "energy-correlation"))
        payload = dict(request.get("payload", {}))
        battery = int(payload.get("battery_percent", self.energy_state.battery_percent))
        execution_type = str(payload.get("execution_type", "")).upper()

        if battery >= 50:
            mode = "STRATEGIC"
        elif battery >= 20:
            mode = "REDUCED"
        else:
            mode = "SILENT"

        allowed = True
        reason = f"{mode}_MODE"
        if mode == "REDUCED" and execution_type == "BACKGROUND_TASK":
            allowed = False
            reason = "BACKGROUND_BLOCKED_REDUCED"
        elif mode == "SILENT" and execution_type not in {"VOICE", "CRITICAL_REMINDER"}:
            allowed = False
            reason = f"{execution_type}_BLOCKED_SILENT"

        self.energy_state.decisions.append(
            {
                "battery_percent": battery,
                "mode": mode,
                "execution_type": execution_type,
                "allowed": allowed,
                "reason": reason,
            }
        )
        return build_energy_result(
            correlation_id=correlation_id,
            allowed=allowed,
            reason=reason,
        )

    @staticmethod
    def _memory_kb() -> float:
        current_bytes, _peak_bytes = tracemalloc.get_traced_memory()
        return float(current_bytes) / 1024.0

    @staticmethod
    def _empty_metrics() -> ExtendedRuntimeMetrics:
        return ExtendedRuntimeMetrics(
            requested_cycles=0,
            completed_cycles=0,
            total_elapsed_ms=0.0,
            average_cycle_latency_ms=0.0,
            max_cycle_latency_ms=0.0,
            min_cycle_latency_ms=0.0,
            latency_samples_ms=(),
            memory_start_kb=0.0,
            memory_mid_kb=0.0,
            memory_end_kb=0.0,
            thread_start_count=threading.active_count(),
            thread_mid_count=threading.active_count(),
            thread_end_count=threading.active_count(),
            asr_model_load_count=0,
            asr_pipeline_build_count=0,
            tts_pipeline_load_count=0,
            llm_allowed_count=0,
            llm_denied_count=0,
            llm_downgraded_count=0,
            unsafe_reasoning_outputs=0,
            proactive_executed_count=0,
            proactive_suppressed_count=0,
            proactive_suppressed_by_cooldown=0,
            sync_event_count=0,
            sync_processed_count=0,
            sync_max_backlog=0,
            sync_invalid_message_count=0,
            voice_allowed_count=0,
            voice_denied_count=0,
            energy_transition_count=0,
            energy_modes_seen=(),
        )


@lru_cache(maxsize=2)
def run_extended_runtime_simulation(total_cycles: int = 10_000) -> ExtendedRuntimeMetrics:
    """Run and cache deterministic long-run runtime simulation."""
    harness = ExtendedRuntimeHarness()
    return harness.run(total_cycles=int(total_cycles))
