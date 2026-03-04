"""Fixtures for internal event flood stability validation."""

from __future__ import annotations

from dataclasses import dataclass
import io
import json
import time
from typing import Any

from services.ipc.rust_bridge import MESSAGE_STATE_UPDATE, RustBridge


@dataclass(frozen=True)
class EventFloodMetrics:
    """Deterministic metrics captured from one internal event flood run."""

    iterations: int
    events_per_iteration: int
    total_published: int
    processed_events: int
    state_updates: int
    duplicate_correlation_count: int
    total_elapsed_ms: float
    average_publish_latency_ms: float
    max_publish_latency_ms: float
    min_publish_latency_ms: float
    latency_samples_ms: tuple[float, ...]


class EventFloodStabilityHarness:
    """Sequential internal-event publisher with deterministic IPC metrics."""

    INTERNAL_EVENT_TYPES = (
        "router_action_event",
        "voice_event",
        "energy_update_event",
        "lifecycle_event",
    )

    def __init__(self) -> None:
        self._processed_payloads: list[dict[str, Any]] = []
        self._state_updates: list[dict[str, Any]] = []
        self._seen_correlation_ids: set[str] = set()
        self._duplicate_correlation_ids: list[str] = []
        self.bridge = RustBridge(
            in_stream=io.StringIO(""),
            out_stream=io.StringIO(),
            event_handler=self._on_event,
        )

    @property
    def processed_events(self) -> int:
        return len(self._processed_payloads)

    @property
    def state_updates(self) -> int:
        return len(self._state_updates)

    @property
    def duplicate_correlation_count(self) -> int:
        return len(self._duplicate_correlation_ids)

    def run_flood(self, *, iterations: int, start_index: int = 0) -> EventFloodMetrics:
        if iterations <= 0:
            return EventFloodMetrics(
                iterations=0,
                events_per_iteration=len(self.INTERNAL_EVENT_TYPES),
                total_published=0,
                processed_events=self.processed_events,
                state_updates=self.state_updates,
                duplicate_correlation_count=self.duplicate_correlation_count,
                total_elapsed_ms=0.0,
                average_publish_latency_ms=0.0,
                max_publish_latency_ms=0.0,
                min_publish_latency_ms=0.0,
                latency_samples_ms=(),
            )

        latencies_ms: list[float] = []
        flood_start = time.perf_counter()

        for offset in range(int(iterations)):
            index = int(start_index) + offset
            for event_type in self.INTERNAL_EVENT_TYPES:
                correlation_id = f"event-flood-{event_type}-{index}"
                line = self._build_event_line(
                    correlation_id=correlation_id,
                    event_type=event_type,
                    sequence=index,
                )
                publish_start = time.perf_counter()
                state_update = self.bridge.process_line(line)
                latencies_ms.append((time.perf_counter() - publish_start) * 1000.0)
                if state_update is not None:
                    self._state_updates.append(dict(state_update))

        total_elapsed_ms = (time.perf_counter() - flood_start) * 1000.0
        total_published = int(iterations) * len(self.INTERNAL_EVENT_TYPES)

        return EventFloodMetrics(
            iterations=int(iterations),
            events_per_iteration=len(self.INTERNAL_EVENT_TYPES),
            total_published=total_published,
            processed_events=self.processed_events,
            state_updates=self.state_updates,
            duplicate_correlation_count=self.duplicate_correlation_count,
            total_elapsed_ms=total_elapsed_ms,
            average_publish_latency_ms=sum(latencies_ms) / len(latencies_ms),
            max_publish_latency_ms=max(latencies_ms),
            min_publish_latency_ms=min(latencies_ms),
            latency_samples_ms=tuple(latencies_ms),
        )

    def _on_event(self, payload: dict[str, Any]) -> None:
        correlation_id = str(payload.get("correlation_id", ""))
        if correlation_id:
            if correlation_id in self._seen_correlation_ids:
                self._duplicate_correlation_ids.append(correlation_id)
            else:
                self._seen_correlation_ids.add(correlation_id)
        self._processed_payloads.append(dict(payload))

    @staticmethod
    def _build_event_line(
        *,
        correlation_id: str,
        event_type: str,
        sequence: int,
    ) -> str:
        return json.dumps(
            {
                "message_type": "EVENT",
                "timestamp": int(time.time() * 1000),
                "correlation_id": correlation_id,
                "payload": {
                    "event": event_type,
                    "correlation_id": correlation_id,
                    "sequence": sequence,
                    "source": "internal",
                },
            },
            separators=(",", ":"),
        )

    def state_update_messages_are_valid(self) -> bool:
        """Return True when all bridge responses are STATE_UPDATE envelopes."""
        return all(
            isinstance(item, dict) and item.get("message_type") == MESSAGE_STATE_UPDATE
            for item in self._state_updates
        )


def build_event_flood_stability_harness() -> EventFloodStabilityHarness:
    """Factory for deterministic internal event flood tests."""
    return EventFloodStabilityHarness()
