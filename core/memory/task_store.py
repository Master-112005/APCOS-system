"""Task persistence with deterministic lifecycle enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3
from typing import Any, Callable, TypeVar
from uuid import uuid4

from core.memory.encryption_layer import EncryptionLayer
from core.memory.lifecycle_manager import (
    InvalidStateTransitionError,
    LifecycleManager,
    TaskState,
)
from services.ipc.rust_bridge import RustBridge

T = TypeVar("T")


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class TaskRecord:
    """Public task model returned by task_store."""

    task_id: int
    title: str
    description: str | None
    goal: str | None
    due_at: str | None
    priority: int
    state: TaskState
    created_at: str
    updated_at: str
    archived_at: str | None


class TaskStore:
    """
    Task CRUD storage backed by SQLite.

    Notes:
    - State transitions are validated via LifecycleManager.
    - Direct permanent deletion is forbidden; archive instead.
    - Sensitive text fields are stored through an encryption stub.
    """

    def __init__(
        self,
        db_path: str | Path = ":memory:",
        encryption_key: str = "apcos-dev-key",
        lifecycle_manager: LifecycleManager | None = None,
        storage_bridge: RustBridge | None = None,
        enforce_storage_authority: bool = False,
        storage_energy_mode: str = "STRATEGIC",
        storage_execution_type: str = "BACKGROUND_TASK",
        memory_bridge: RustBridge | None = None,
        enforce_memory_authority: bool = False,
        memory_energy_mode: str = "STRATEGIC",
    ) -> None:
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._encryption = EncryptionLayer(encryption_key)
        key_digest = hashlib.sha256(encryption_key.encode("utf-8")).hexdigest()[:16]
        self._storage_encryption_key_id = f"python-{key_digest}"
        self._lifecycle = lifecycle_manager or LifecycleManager()
        self._storage_bridge = storage_bridge
        self._enforce_storage_authority = bool(enforce_storage_authority)
        self._storage_energy_mode = storage_energy_mode
        self._storage_execution_type = storage_execution_type
        self._memory_bridge = memory_bridge or storage_bridge
        self._enforce_memory_authority = bool(enforce_memory_authority)
        self._memory_energy_mode = memory_energy_mode
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title_enc TEXT NOT NULL,
                description_enc TEXT,
                goal_enc TEXT,
                due_at TEXT,
                priority INTEGER NOT NULL DEFAULT 0,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                archived_at TEXT
            );
            """
        )
        self._conn.commit()

    def create_task(
        self,
        title: str,
        description: str | None = None,
        due_at: str | None = None,
        goal: str | None = None,
        priority: int = 0,
    ) -> TaskRecord:
        """Create a task in CREATED state."""
        cleaned_title = title.strip()
        if not cleaned_title:
            raise ValueError("title must not be empty")

        timestamp = utc_now_iso()
        task_id = self._validate_storage_and_maybe_execute(
            operation="WRITE_TASK",
            lifecycle_state=TaskState.CREATED.value,
            execute_callable=lambda: self._create_task_row(
                cleaned_title=cleaned_title,
                description=description,
                goal=goal,
                due_at=due_at,
                priority=priority,
                timestamp=timestamp,
            ),
        )
        return self.get_task(task_id)

    def get_task(self, task_id: int) -> TaskRecord | None:
        """Fetch a task by id."""
        row = self._conn.execute("SELECT * FROM tasks WHERE id = ?;", (task_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def list_tasks(self, include_archived: bool = False) -> list[TaskRecord]:
        """Return task list ordered by newest first."""
        if include_archived:
            rows = self._conn.execute("SELECT * FROM tasks ORDER BY id DESC;").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM tasks WHERE state != ? ORDER BY id DESC;",
                (TaskState.ARCHIVED.value,),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def update_task(
        self,
        task_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
        goal: str | None = None,
        due_at: str | None = None,
        priority: int | None = None,
    ) -> TaskRecord:
        """Update mutable non-state task fields."""
        current = self.get_task(task_id)
        if current is None:
            raise KeyError(f"Task {task_id} not found")

        updated_title = title.strip() if title is not None else current.title
        if not updated_title:
            raise ValueError("title must not be empty")

        updated_description = (
            description.strip() if description is not None else current.description
        )
        updated_goal = goal.strip() if goal is not None else current.goal
        updated_due_at = due_at if due_at is not None else current.due_at
        updated_priority = int(priority) if priority is not None else current.priority

        self._validate_storage_and_maybe_execute(
            operation="UPDATE_TASK",
            lifecycle_state=current.state.value,
            execute_callable=lambda: self._update_task_row(
                task_id=task_id,
                title=updated_title,
                description=updated_description,
                goal=updated_goal,
                due_at=updated_due_at,
                priority=updated_priority,
            ),
        )
        return self.get_task(task_id)

    def transition_task(self, task_id: int, new_state: str | TaskState) -> TaskRecord:
        """Transition a task state through lifecycle rules."""
        current = self.get_task(task_id)
        if current is None:
            raise KeyError(f"Task {task_id} not found")

        destination = self._lifecycle.normalize_state(new_state)
        now = utc_now_iso()
        archived_at = now if destination == TaskState.ARCHIVED else current.archived_at

        storage_operation = self._storage_operation_for_destination(destination)
        memory_operation = self._memory_operation_for_transition(
            current_state=current.state,
            destination_state=destination,
        )
        self._validate_memory_and_maybe_transition(
            task_id=task_id,
            current_state=current.state,
            destination=destination,
            memory_operation=memory_operation,
            storage_operation=storage_operation,
            lifecycle_state=current.state.value,
            execute_callable=lambda: self._transition_task_row(
                task_id=task_id,
                destination=destination,
                updated_at=now,
                archived_at=archived_at,
            ),
        )
        return self.get_task(task_id)

    def activate_task(self, task_id: int) -> TaskRecord:
        """Convenience lifecycle transition to ACTIVE."""
        return self.transition_task(task_id, TaskState.ACTIVE)

    def complete_task(self, task_id: int) -> TaskRecord:
        """Convenience lifecycle transition to COMPLETED."""
        return self.transition_task(task_id, TaskState.COMPLETED)

    def archive_task(self, task_id: int) -> TaskRecord:
        """Archive a task (replacement for permanent delete)."""
        return self.transition_task(task_id, TaskState.ARCHIVED)

    def delete_task(self, task_id: int) -> None:
        """Prevent permanent deletion by policy."""
        raise RuntimeError(
            f"Permanent deletion disabled for task {task_id}; use archive_task instead."
        )

    def close(self) -> None:
        """Close SQLite connection."""
        self._conn.close()

    def __enter__(self) -> "TaskStore":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _row_to_record(self, row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            task_id=int(row["id"]),
            title=self._encryption.decrypt(row["title_enc"]) or "",
            description=self._encryption.decrypt(row["description_enc"]),
            goal=self._encryption.decrypt(row["goal_enc"]),
            due_at=row["due_at"],
            priority=int(row["priority"]),
            state=TaskState(row["state"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            archived_at=row["archived_at"],
        )

    def _create_task_row(
        self,
        *,
        cleaned_title: str,
        description: str | None,
        goal: str | None,
        due_at: str | None,
        priority: int,
        timestamp: str,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO tasks (
                title_enc,
                description_enc,
                goal_enc,
                due_at,
                priority,
                state,
                created_at,
                updated_at,
                archived_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL);
            """,
            (
                self._encryption.encrypt(cleaned_title),
                self._encryption.encrypt(description.strip()) if description else None,
                self._encryption.encrypt(goal.strip()) if goal else None,
                due_at,
                int(priority),
                TaskState.CREATED.value,
                timestamp,
                timestamp,
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def _update_task_row(
        self,
        *,
        task_id: int,
        title: str,
        description: str | None,
        goal: str | None,
        due_at: str | None,
        priority: int,
    ) -> None:
        self._conn.execute(
            """
            UPDATE tasks
            SET
                title_enc = ?,
                description_enc = ?,
                goal_enc = ?,
                due_at = ?,
                priority = ?,
                updated_at = ?
            WHERE id = ?;
            """,
            (
                self._encryption.encrypt(title),
                self._encryption.encrypt(description) if description is not None else None,
                self._encryption.encrypt(goal) if goal is not None else None,
                due_at,
                priority,
                utc_now_iso(),
                task_id,
            ),
        )
        self._conn.commit()

    def _transition_task_row(
        self,
        *,
        task_id: int,
        destination: TaskState,
        updated_at: str,
        archived_at: str | None,
    ) -> None:
        self._conn.execute(
            """
            UPDATE tasks
            SET state = ?, updated_at = ?, archived_at = ?
            WHERE id = ?;
            """,
            (destination.value, updated_at, archived_at, task_id),
        )
        self._conn.commit()

    @staticmethod
    def _storage_operation_for_destination(destination: TaskState) -> str:
        return "ARCHIVE_TASK" if destination == TaskState.ARCHIVED else "UPDATE_TASK"

    @staticmethod
    def _memory_operation_for_transition(
        *,
        current_state: TaskState,
        destination_state: TaskState,
    ) -> str:
        if destination_state == TaskState.ACTIVE:
            return "PROMOTE_TO_ACTIVE"
        if destination_state == TaskState.COMPLETED:
            return "DEMOTE_TO_DORMANT"
        if destination_state == TaskState.ARCHIVED and current_state == TaskState.ARCHIVED:
            return "FINALIZE_ARCHIVE"
        if destination_state == TaskState.ARCHIVED:
            return "ARCHIVE_ITEM"
        return "RETENTION_TRIGGER"

    def _validate_memory_and_maybe_transition(
        self,
        *,
        task_id: int,
        current_state: TaskState,
        destination: TaskState,
        memory_operation: str,
        storage_operation: str,
        lifecycle_state: str,
        execute_callable: Callable[[], T],
    ) -> T:
        if self._memory_bridge is None:
            if self._enforce_memory_authority:
                raise InvalidStateTransitionError(
                    f"Invalid transition for task {task_id}: memory authority unavailable"
                )
            self._lifecycle.assert_transition(task_id, current_state, destination)
            return self._validate_storage_and_maybe_execute(
                operation=storage_operation,
                lifecycle_state=lifecycle_state,
                execute_callable=execute_callable,
            )

        storage_permission_flag = self._request_storage_permission(
            operation=storage_operation,
            lifecycle_state=lifecycle_state,
        )
        allowed, result, reason = self._memory_bridge.validate_memory_and_maybe_transition(
            current_lifecycle_state=current_state.value,
            operation=memory_operation,
            energy_mode=self._memory_energy_mode,
            storage_permission_flag=storage_permission_flag,
            metadata_flags={
                "critical_reminder": False,
                "allow_archived_reactivation": False,
                "retention_due": destination == TaskState.ARCHIVED,
            },
            correlation_id=f"memory-{uuid4()}",
            transition_callable=lambda: self._execute_authorized_transition(
                task_id=task_id,
                current_state=current_state,
                destination=destination,
                storage_operation=storage_operation,
                lifecycle_state=lifecycle_state,
                execute_callable=execute_callable,
            ),
        )
        if not allowed:
            detail = reason or "MEMORY_TRANSITION_DENIED"
            raise InvalidStateTransitionError(
                f"Invalid transition for task {task_id}: {current_state.value} -> {destination.value} ({detail})"
            )
        return result

    def _execute_authorized_transition(
        self,
        *,
        task_id: int,
        current_state: TaskState,
        destination: TaskState,
        storage_operation: str,
        lifecycle_state: str,
        execute_callable: Callable[[], T],
    ) -> T:
        self._lifecycle.record_transition(task_id, current_state, destination)
        return self._validate_storage_and_maybe_execute(
            operation=storage_operation,
            lifecycle_state=lifecycle_state,
            execute_callable=execute_callable,
        )

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
            encryption_key_id=self._storage_encryption_key_id,
            correlation_id=f"storage-preflight-{uuid4()}",
        )
        payload = response.get("payload", {})
        return bool(payload.get("allowed", False))

    def _validate_storage_and_maybe_execute(
        self,
        *,
        operation: str,
        lifecycle_state: str,
        execute_callable: Callable[[], T],
    ) -> T:
        if self._storage_bridge is None:
            if self._enforce_storage_authority:
                raise RuntimeError("Storage authority unavailable")
            return execute_callable()

        correlation_id = f"storage-{uuid4()}"
        allowed, result, reason = self._storage_bridge.validate_storage_and_maybe_execute(
            operation=operation,
            lifecycle_state=lifecycle_state,
            energy_mode=self._storage_energy_mode,
            execution_type=self._storage_execution_type,
            encryption_metadata_present=True,
            encryption_key_id=self._storage_encryption_key_id,
            correlation_id=correlation_id,
            execute_callable=execute_callable,
        )
        if not allowed:
            raise RuntimeError(f"Storage authority denied: {reason or 'STORAGE_DENIED'}")
        return result
