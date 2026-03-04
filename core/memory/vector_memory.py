"""Vector memory adapter with optional Rust storage authority checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from uuid import uuid4

from services.ipc.rust_bridge import RustBridge


@dataclass(frozen=True)
class VectorRecord:
    """Immutable vector payload container."""

    vector_id: str
    embedding: tuple[float, ...]
    metadata: dict[str, str]


class VectorMemory:
    """
    In-process vector cache.

    Stage 15 note:
    - Rust remains the authority for storage mutation permission.
    - This module executes writes only after storage validation when a bridge is
      configured.
    """

    def __init__(
        self,
        *,
        storage_bridge: RustBridge | None = None,
        enforce_storage_authority: bool = False,
        storage_energy_mode: str = "STRATEGIC",
        storage_execution_type: str = "BACKGROUND_TASK",
        encryption_key_id: str = "vector-default-key",
        memory_bridge: RustBridge | None = None,
        enforce_memory_authority: bool = False,
        memory_energy_mode: str = "STRATEGIC",
    ) -> None:
        self._storage_bridge = storage_bridge
        self._enforce_storage_authority = bool(enforce_storage_authority)
        self._storage_energy_mode = storage_energy_mode
        self._storage_execution_type = storage_execution_type
        self._encryption_key_id = encryption_key_id
        self._memory_bridge = memory_bridge or storage_bridge
        self._enforce_memory_authority = bool(enforce_memory_authority)
        self._memory_energy_mode = memory_energy_mode
        self._records: dict[str, VectorRecord] = {}

    def upsert(
        self,
        *,
        vector_id: str,
        embedding: list[float],
        metadata: dict[str, str] | None = None,
    ) -> VectorRecord:
        """Store vector record after storage policy validation."""
        normalized = tuple(float(value) for value in embedding)
        payload = VectorRecord(
            vector_id=vector_id,
            embedding=normalized,
            metadata=dict(metadata or {}),
        )
        return self._validate_memory_and_maybe_transition(
            operation="VECTOR_TIER_SHIFT",
            current_lifecycle_state="ACTIVE",
            storage_operation="VECTOR_WRITE",
            transition_callable=lambda: self._validate_storage_and_maybe_execute(
                operation="VECTOR_WRITE",
                lifecycle_state="CREATED",
                execute_callable=lambda: self._write(payload),
            ),
        )

    def delete(self, vector_id: str) -> bool:
        """Delete vector record after storage policy validation."""
        return self._validate_memory_and_maybe_transition(
            operation="VECTOR_TIER_SHIFT",
            current_lifecycle_state="DORMANT",
            storage_operation="VECTOR_DELETE",
            transition_callable=lambda: self._validate_storage_and_maybe_execute(
                operation="VECTOR_DELETE",
                lifecycle_state="CREATED",
                execute_callable=lambda: self._delete(vector_id),
            ),
        )

    def get(self, vector_id: str) -> VectorRecord | None:
        """Read vector without mutation."""
        return self._records.get(vector_id)

    def _write(self, payload: VectorRecord) -> VectorRecord:
        self._records[payload.vector_id] = payload
        return payload

    def _delete(self, vector_id: str) -> bool:
        return self._records.pop(vector_id, None) is not None

    def _validate_storage_and_maybe_execute(
        self,
        *,
        operation: str,
        lifecycle_state: str,
        execute_callable: Callable[[], object],
    ):
        if self._storage_bridge is None:
            if self._enforce_storage_authority:
                raise RuntimeError("Storage authority unavailable")
            return execute_callable()

        allowed, result, reason = self._storage_bridge.validate_storage_and_maybe_execute(
            operation=operation,
            lifecycle_state=lifecycle_state,
            energy_mode=self._storage_energy_mode,
            execution_type=self._storage_execution_type,
            encryption_metadata_present=True,
            encryption_key_id=self._encryption_key_id,
            correlation_id=f"storage-vector-{uuid4()}",
            execute_callable=execute_callable,
        )
        if not allowed:
            raise RuntimeError(f"Storage authority denied: {reason or 'STORAGE_DENIED'}")
        return result

    def _validate_memory_and_maybe_transition(
        self,
        *,
        operation: str,
        current_lifecycle_state: str,
        storage_operation: str,
        transition_callable: Callable[[], object],
    ):
        if self._memory_bridge is None:
            if self._enforce_memory_authority:
                raise RuntimeError("Memory authority unavailable")
            return transition_callable()

        storage_permission_flag = self._request_storage_permission(
            operation=storage_operation,
            lifecycle_state="CREATED",
        )
        allowed, result, reason = self._memory_bridge.validate_memory_and_maybe_transition(
            current_lifecycle_state=current_lifecycle_state,
            operation=operation,
            energy_mode=self._memory_energy_mode,
            storage_permission_flag=storage_permission_flag,
            metadata_flags={
                "critical_reminder": False,
                "allow_archived_reactivation": False,
                "retention_due": False,
            },
            correlation_id=f"memory-vector-{uuid4()}",
            transition_callable=transition_callable,
        )
        if not allowed:
            raise RuntimeError(f"Memory authority denied: {reason or 'MEMORY_DENIED'}")
        return result

    def _request_storage_permission(
        self,
        *,
        operation: str,
        lifecycle_state: str,
    ) -> bool:
        if self._storage_bridge is None:
            return not self._enforce_storage_authority

        response = self._storage_bridge.request_storage_validation(
            operation=operation,
            lifecycle_state=lifecycle_state,
            energy_mode=self._storage_energy_mode,
            execution_type=self._storage_execution_type,
            encryption_metadata_present=True,
            encryption_key_id=self._encryption_key_id,
            correlation_id=f"storage-vector-preflight-{uuid4()}",
        )
        payload = response.get("payload", {})
        return bool(payload.get("allowed", False))
