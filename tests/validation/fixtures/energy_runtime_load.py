"""Fixtures for behavioral energy-runtime validation scenarios."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import io
from typing import Any, Iterator
from uuid import uuid4

from core.cognition.challenge_logic import ChallengeLogic
from core.cognition.command_router import CommandRouter
from core.cognition.reasoning_engine import ReasoningEngine
from core.cognition.proactive_controller import ProactiveController
from core.memory.lifecycle_manager import LifecycleManager
from core.memory.task_store import TaskStore
from services.ipc.rust_bridge import RustBridge, build_energy_result
from services.sync_daemon import SyncDaemon
from voice.voice_session import VoiceSession
from voice.wake_word import WakeWordDetector


@dataclass
class MockEnergyState:
    """Deterministic mutable battery model for test-time energy authority checks."""

    battery_percent: int = 60
    decisions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def mode(self) -> str:
        if self.battery_percent >= 50:
            return "NORMAL"
        if self.battery_percent >= 20:
            return "REDUCED"
        return "CRITICAL"

    def set_battery(self, value: int) -> None:
        self.battery_percent = max(0, min(100, int(value)))


class CaptureBridge:
    """Simple in-memory sink for forwarded SyncDaemon envelopes."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def send_message(self, message: dict[str, Any]) -> None:
        self.messages.append(dict(message))

    def publish_event(self, message: dict[str, Any]) -> None:
        self.messages.append(dict(message))


class MockTTS:
    """Deterministic TTS stub used to validate voice output continuity."""

    def __init__(self) -> None:
        self.spoken: list[str] = []

    def speak(self, text: str) -> bytes:
        clean = str(text)
        self.spoken.append(clean)
        return clean.encode("utf-8")


class _EnergyAwareVoiceController:
    """Test-time controller that gates heavy voice cognition through energy authority."""

    def __init__(self, harness: "EnergyRuntimeHarness") -> None:
        self._harness = harness
        self._identity: Any = None

    def set_identity(self, identity: Any) -> None:
        self._identity = identity

    def handle_input(self, user_text: str) -> str:
        text = (user_text or "").strip()
        if text.lower().startswith("/strategy"):
            query = text[len("/strategy") :].strip() or "strategy"
            result = self._harness.run_reasoning(query)
            if not result["allowed"]:
                return f"Energy gate: {result['reason']}"
            return f"Strategy: {result['summary']}"

        allowed, response, reason = self._harness.bridge.validate_energy_and_maybe_execute(
            battery_percent=self._harness.energy_state.battery_percent,
            execution_type="VOICE",
            correlation_id=f"energy-voice-{uuid4()}",
            execute_callable=lambda: "Voice command acknowledged.",
        )
        if not allowed:
            return f"Energy gate: {reason}"
        return str(response)


class EnergyRuntimeHarness:
    """Unified harness for A3 tests: reasoning, proactive, voice, sync, energy gating."""

    def __init__(self) -> None:
        self.energy_state = MockEnergyState()
        self.sync_bridge = CaptureBridge()
        self.sync_daemon = SyncDaemon(self.sync_bridge)
        self.lifecycle = LifecycleManager()
        self.store = TaskStore(lifecycle_manager=self.lifecycle)
        self.router = CommandRouter(
            task_store=self.store,
            lifecycle_manager=self.lifecycle,
            challenge_logic=ChallengeLogic(),
            config_path="configs/default.yaml",
        )
        self.reasoning_engine = ReasoningEngine()
        self.proactive_controller = ProactiveController(confidence_threshold=0.7, daily_limit=12)
        self.bridge = RustBridge(
            in_stream=io.StringIO(""),
            out_stream=io.StringIO(),
            energy_transport=self._energy_transport,
        )
        self.voice_controller = _EnergyAwareVoiceController(self)

    def set_battery(self, percent: int) -> None:
        self.energy_state.set_battery(percent)

    def router_audit_count(self) -> int:
        return len(self.router.get_audit_events())

    def sync_burst(self, *, count: int, source_prefix: str = "sync-source") -> None:
        for index in range(int(count)):
            self.sync_daemon.receive_sync(
                {
                    "source_id": f"{source_prefix}-{index % 3}",
                    "sync_type": "STATE_RECONCILE",
                    "payload": {"revision": index},
                    "timestamp": datetime.now(timezone.utc).timestamp(),
                    "correlation_id": f"sync-energy-{uuid4()}",
                    "merge_hint": {
                        "source_priority": "normal",
                        "version": "v1",
                        "external_timestamp": datetime.now(timezone.utc).timestamp(),
                    },
                }
            )

    def run_reasoning(self, query: str) -> dict[str, Any]:
        battery = self.energy_state.battery_percent
        mode = self.energy_state.mode
        validation = self.bridge.request_energy_validation(
            battery_percent=battery,
            execution_type="LLM",
            correlation_id=f"energy-llm-{uuid4()}",
        )
        payload = dict(validation["payload"])
        if not bool(payload.get("allowed", False)):
            return {
                "allowed": False,
                "mode": mode,
                "downgraded": False,
                "summary": "",
                "steps": (),
                "reason": str(payload.get("reason") or "ENERGY_DENIED"),
            }

        if mode == "REDUCED":
            output = self.reasoning_engine.generate_strategy(
                {
                    "goal": query[:64],
                    "horizon_days": 1,
                    "constraints": "reduced-power-mode",
                }
            )
            steps = output.strategy_steps[:1]
            summary = output.summary
            return {
                "allowed": True,
                "mode": mode,
                "downgraded": True,
                "summary": summary,
                "steps": steps,
                "reason": None,
            }

        output = self.reasoning_engine.generate_strategy(
            {"goal": query, "notes": query, "horizon_days": 7}
        )
        return {
            "allowed": True,
            "mode": mode,
            "downgraded": False,
            "summary": output.summary,
            "steps": output.strategy_steps,
            "reason": None,
        }

    def run_proactive_cycle(self, context: dict[str, Any]) -> dict[str, Any]:
        allowed, suggestions, reason = self.bridge.validate_energy_and_maybe_execute(
            battery_percent=self.energy_state.battery_percent,
            execution_type="PROACTIVE",
            correlation_id=f"energy-proactive-{uuid4()}",
            execute_callable=lambda: self.proactive_controller.evaluate(context),
        )
        if not allowed:
            return {"status": "skipped", "reason": reason, "suggestions": []}
        return {"status": "executed", "reason": None, "suggestions": list(suggestions or [])}

    def build_voice_session(self, *, transcript: str) -> VoiceSession:
        events: Iterator[str] = iter(["hey apcos"])
        detector = WakeWordDetector(event_source=lambda: next(events, None))
        audio = f"tier:owner;text:{transcript}".encode("utf-8")
        return VoiceSession(
            wake_word_detector=detector,
            interaction_controller=self.voice_controller,
            audio_capture=lambda: audio,
        )

    def _energy_transport(self, request: dict[str, Any]) -> dict[str, Any]:
        correlation_id = str(request.get("correlation_id", "energy-correlation"))
        payload = dict(request.get("payload", {}))
        battery = int(payload.get("battery_percent", self.energy_state.battery_percent))
        execution_type = str(payload.get("execution_type", "")).upper()

        if battery >= 50:
            mode = "NORMAL"
        elif battery >= 20:
            mode = "REDUCED"
        else:
            mode = "CRITICAL"

        allowed = True
        reason = f"{mode}_MODE"
        if mode == "REDUCED" and execution_type == "BACKGROUND_TASK":
            allowed = False
            reason = "BACKGROUND_BLOCKED_REDUCED"
        elif mode == "CRITICAL" and execution_type not in {"VOICE", "CRITICAL_REMINDER"}:
            allowed = False
            reason = f"{execution_type}_BLOCKED_CRITICAL"

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


def build_energy_runtime_harness() -> EnergyRuntimeHarness:
    """Factory for Step A3 deterministic runtime harness."""
    return EnergyRuntimeHarness()

