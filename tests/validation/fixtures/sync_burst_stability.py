"""Fixtures for high-frequency sync burst stability validation."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import time
from typing import Any

from core.connectors.mobile_connector import MobileConnector
from services.sync_daemon import SyncDaemon


@dataclass(frozen=True)
class SyncBurstMetrics:
    """Deterministic metrics captured from one sync burst run."""

    sync_sent: int
    mobile_sent: int
    total_sent: int
    processed_count: int
    duplicate_count: int
    max_queue_depth: int
    overflow_detected: bool
    pending_queue: int
    average_latency_ms: float
    max_latency_ms: float
    min_latency_ms: float
    total_elapsed_ms: float
    latency_samples_ms: tuple[float, ...]


class BoundedQueueBridge:
    """In-memory queue bridge to emulate event bus buffering under load."""

    def __init__(
        self,
        *,
        max_queue_size: int = 256,
        drain_every: int = 8,
        drain_batch_size: int = 6,
    ) -> None:
        self.max_queue_size = max(1, int(max_queue_size))
        self.drain_every = max(1, int(drain_every))
        self.drain_batch_size = max(1, int(drain_batch_size))

        self._queue: deque[dict[str, Any]] = deque()
        self.messages: list[dict[str, Any]] = []
        self.max_depth_seen = 0
        self.overflow_detected = False
        self._enqueued_count = 0
        self._processed_count = 0
        self._seen_correlation_ids: set[str] = set()
        self._duplicate_correlation_ids: list[str] = []

    def publish_event(self, message: dict[str, Any]) -> None:
        self._enqueue(message)

    def send_message(self, message: dict[str, Any]) -> None:
        self._enqueue(message)

    def flush(self) -> None:
        self._drain(count=len(self._queue))

    @property
    def processed_count(self) -> int:
        return self._processed_count

    @property
    def duplicate_count(self) -> int:
        return len(self._duplicate_correlation_ids)

    @property
    def pending_queue(self) -> int:
        return len(self._queue)

    def _enqueue(self, message: dict[str, Any]) -> None:
        snapshot = dict(message)
        self._queue.append(snapshot)
        self._enqueued_count += 1

        depth = len(self._queue)
        if depth > self.max_depth_seen:
            self.max_depth_seen = depth
        if depth > self.max_queue_size:
            self.overflow_detected = True

        if self._enqueued_count % self.drain_every == 0:
            self._drain(count=self.drain_batch_size)

    def _drain(self, *, count: int) -> None:
        for _ in range(min(count, len(self._queue))):
            item = self._queue.popleft()
            correlation = item.get("correlation_id")
            if isinstance(correlation, str):
                if correlation in self._seen_correlation_ids:
                    self._duplicate_correlation_ids.append(correlation)
                else:
                    self._seen_correlation_ids.add(correlation)
            self.messages.append(item)
            self._processed_count += 1


class SyncBurstStabilityHarness:
    """High-frequency sync and mobile ingress harness with queue metrics."""

    def __init__(
        self,
        *,
        max_queue_size: int = 256,
        drain_every: int = 8,
        drain_batch_size: int = 6,
    ) -> None:
        self.bridge = BoundedQueueBridge(
            max_queue_size=max_queue_size,
            drain_every=drain_every,
            drain_batch_size=drain_batch_size,
        )
        self.sync_daemon = SyncDaemon(self.bridge)
        self.mobile_connector = MobileConnector(self.bridge)

    def run_burst(self, *, iterations: int, mobile_every: int) -> SyncBurstMetrics:
        if iterations <= 0:
            return SyncBurstMetrics(
                sync_sent=0,
                mobile_sent=0,
                total_sent=0,
                processed_count=0,
                duplicate_count=0,
                max_queue_depth=0,
                overflow_detected=False,
                pending_queue=0,
                average_latency_ms=0.0,
                max_latency_ms=0.0,
                min_latency_ms=0.0,
                total_elapsed_ms=0.0,
                latency_samples_ms=(),
            )

        mobile_interval = max(1, int(mobile_every))
        sync_sent = 0
        mobile_sent = 0
        latencies_ms: list[float] = []
        burst_start = time.perf_counter()

        for index in range(int(iterations)):
            sync_start = time.perf_counter()
            self.sync_daemon.receive_sync(
                {
                    "source_id": f"sync-source-{index % 5}",
                    "sync_type": "TASK_UPDATE",
                    "payload": {"external_task_id": f"ext-{index}", "sequence": index},
                    "correlation_id": f"sync-burst-{index}",
                    "merge_hint": {
                        "source_priority": "normal",
                        "version": "v1",
                        "external_timestamp": 1700000000 + index,
                    },
                }
            )
            latencies_ms.append((time.perf_counter() - sync_start) * 1000.0)
            sync_sent += 1

            if index % mobile_interval == 0:
                mobile_start = time.perf_counter()
                self.mobile_connector.receive_event(
                    {
                        "action": "create_task",
                        "payload": {"task": f"Task {index}", "sequence": index},
                        "correlation_id": f"mobile-burst-{index}",
                    }
                )
                latencies_ms.append((time.perf_counter() - mobile_start) * 1000.0)
                mobile_sent += 1

        self.bridge.flush()
        total_elapsed_ms = (time.perf_counter() - burst_start) * 1000.0

        average_latency_ms = sum(latencies_ms) / len(latencies_ms)
        max_latency_ms = max(latencies_ms)
        min_latency_ms = min(latencies_ms)
        total_sent = sync_sent + mobile_sent
        return SyncBurstMetrics(
            sync_sent=sync_sent,
            mobile_sent=mobile_sent,
            total_sent=total_sent,
            processed_count=self.bridge.processed_count,
            duplicate_count=self.bridge.duplicate_count,
            max_queue_depth=self.bridge.max_depth_seen,
            overflow_detected=self.bridge.overflow_detected,
            pending_queue=self.bridge.pending_queue,
            average_latency_ms=average_latency_ms,
            max_latency_ms=max_latency_ms,
            min_latency_ms=min_latency_ms,
            total_elapsed_ms=total_elapsed_ms,
            latency_samples_ms=tuple(latencies_ms),
        )


def build_sync_burst_stability_harness(
    *,
    max_queue_size: int = 256,
    drain_every: int = 8,
    drain_batch_size: int = 6,
) -> SyncBurstStabilityHarness:
    """Factory for deterministic sync burst stability tests."""
    return SyncBurstStabilityHarness(
        max_queue_size=max_queue_size,
        drain_every=drain_every,
        drain_batch_size=drain_batch_size,
    )
