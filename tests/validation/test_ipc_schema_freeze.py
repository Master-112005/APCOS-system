from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from services.ipc import rust_bridge


EXPECTED_MESSAGE_TYPES = (
    "EVENT",
    "STATE_UPDATE",
    "AUTH_REQUEST",
    "AUTH_RESULT",
    "TRANSITION_VALIDATE",
    "TRANSITION_RESULT",
    "ENERGY_VALIDATE",
    "ENERGY_RESULT",
    "STORAGE_VALIDATE",
    "STORAGE_RESULT",
    "MEMORY_VALIDATE",
    "MEMORY_RESULT",
)
EXPECTED_SCHEMA_HASH = "c09551172475a39e3c22a37a88ecfec5e68015d21ddd635a74600a6f2decf374"


def _schema_descriptor() -> dict[str, object]:
    return {
        "schema_version": rust_bridge.IPC_SCHEMA_VERSION,
        "envelope_keys": ("message_type", "timestamp", "correlation_id", "payload"),
        "message_types": EXPECTED_MESSAGE_TYPES,
        "max_message_bytes": rust_bridge.MAX_MESSAGE_BYTES,
    }


def _schema_hash() -> str:
    encoded = json.dumps(_schema_descriptor(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def test_ipc_schema_version_constant_locked() -> None:
    assert rust_bridge.IPC_SCHEMA_VERSION == 1

    root = Path(__file__).resolve().parents[2]
    ipc_rs = root / "os" / "src" / "ipc.rs"
    source = ipc_rs.read_text(encoding="utf-8")
    match = re.search(r"pub const IPC_SCHEMA_VERSION:\s*u16\s*=\s*(\d+)\s*;", source)
    assert match is not None
    assert int(match.group(1)) == rust_bridge.IPC_SCHEMA_VERSION


def test_ipc_message_types_locked() -> None:
    observed = (
        rust_bridge.MESSAGE_EVENT,
        rust_bridge.MESSAGE_STATE_UPDATE,
        rust_bridge.MESSAGE_AUTH_REQUEST,
        rust_bridge.MESSAGE_AUTH_RESULT,
        rust_bridge.MESSAGE_TRANSITION_VALIDATE,
        rust_bridge.MESSAGE_TRANSITION_RESULT,
        rust_bridge.MESSAGE_ENERGY_VALIDATE,
        rust_bridge.MESSAGE_ENERGY_RESULT,
        rust_bridge.MESSAGE_STORAGE_VALIDATE,
        rust_bridge.MESSAGE_STORAGE_RESULT,
        rust_bridge.MESSAGE_MEMORY_VALIDATE,
        rust_bridge.MESSAGE_MEMORY_RESULT,
    )
    assert observed == EXPECTED_MESSAGE_TYPES


def test_ipc_schema_hash_locked() -> None:
    assert _schema_hash() == EXPECTED_SCHEMA_HASH
