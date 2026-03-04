"""Export frozen APCOS contract snapshots for device integration."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "deployment" / "contracts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ipc import rust_bridge


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse_enum_variants(source: str, enum_name: str) -> list[str]:
    pattern = re.compile(rf"pub enum {re.escape(enum_name)}\s*\{{(?P<body>.*?)\n\}}", re.DOTALL)
    match = pattern.search(source)
    if match is None:
        return []

    variants: list[str] = []
    for line in match.group("body").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("#"):
            continue
        variant = stripped.split("(")[0].split("=")[0].rstrip(",").strip()
        if variant:
            variants.append(variant)
    return variants


def _extract_string_literals(source: str, pattern: str) -> list[str]:
    values = re.findall(pattern, source)
    ordered: list[str] = []
    for value in values:
        if value not in ordered:
            ordered.append(value)
    return ordered


def _parse_tier_actions(source: str, tier_name: str) -> list[str]:
    pattern = re.compile(
        rf"Tier::{re.escape(tier_name)}\s*=>\s*matches!\(\s*action_name\.as_str\(\),(?P<body>.*?)\),",
        re.DOTALL,
    )
    match = pattern.search(source)
    if match is None:
        if tier_name == "Guest":
            return []
        return []
    return _extract_string_literals(match.group("body"), r'"([A-Z_]+)"')


def _parse_lifecycle_transitions(source: str) -> list[dict[str, str]]:
    pre_test = source.split("#[cfg(test)]", 1)[0]
    pairs = re.findall(r"\(TaskState::(\w+),\s*TaskState::(\w+)\)", pre_test)
    transitions: list[dict[str, str]] = []
    for from_state, to_state in pairs:
        item = {"from": from_state, "to": to_state}
        if item not in transitions:
            transitions.append(item)
    return transitions


def _parse_energy_thresholds(source: str) -> dict[str, float]:
    keys = (
        "cpu_high_percent",
        "battery_low_percent",
        "battery_critical_percent",
        "thermal_high_celsius",
        "thermal_critical_celsius",
        "thermal_recovery_cycles",
    )
    thresholds: dict[str, float] = {}
    for key in keys:
        match = re.search(rf"{re.escape(key)}:\s*([0-9.]+)", source)
        if match is not None:
            thresholds[key] = float(match.group(1))
    return thresholds


def _build_authority_snapshot() -> dict[str, Any]:
    lifecycle_src = _read(ROOT / "os" / "src" / "runtime" / "lifecycle.rs")
    energy_src = _read(ROOT / "os" / "src" / "energy_manager.rs")
    storage_src = _read(ROOT / "os" / "src" / "secure_storage.rs")
    memory_src = _read(ROOT / "os" / "src" / "runtime" / "memory_authority.rs")
    tier_policy_src = _read(ROOT / "os" / "src" / "identity" / "tier_policy.rs")
    ipc_src = _read(ROOT / "os" / "src" / "ipc.rs")

    ipc_schema_version_match = re.search(r"pub const IPC_SCHEMA_VERSION:\s*u16\s*=\s*(\d+)", ipc_src)
    ipc_schema_version = int(ipc_schema_version_match.group(1)) if ipc_schema_version_match else 0

    lifecycle_states = _parse_enum_variants(lifecycle_src, "TaskState")
    lifecycle_pre_test = lifecycle_src.split("#[cfg(test)]", 1)[0]
    lifecycle_reasons = _extract_string_literals(
        lifecycle_pre_test,
        r'reason:\s*Some\("([A-Z_]+)"',
    )

    energy_modes = _parse_enum_variants(energy_src, "EnergyMode")
    execution_types = _parse_enum_variants(energy_src, "ExecutionType")
    energy_reason_codes = _extract_string_literals(energy_src, r'reason:\s*Some\("([A-Z_]+)"')

    storage_operations = _parse_enum_variants(storage_src, "StorageOperation")
    storage_reason_codes = _extract_string_literals(
        storage_src,
        r'StorageDecision::deny\(\s*"([A-Z_]+)"',
    )

    memory_operations = _parse_enum_variants(memory_src, "MemoryOperation")
    memory_reason_codes = _extract_string_literals(
        memory_src,
        r'MemoryDecision::deny\(\s*"([A-Z_]+)"',
    )

    identity_tiers = _parse_enum_variants(tier_policy_src, "Tier")

    return {
        "ipc_schema_version": ipc_schema_version,
        "identity": {
            "tiers": identity_tiers,
            "policy_matrix": {
                "Owner": _parse_tier_actions(tier_policy_src, "Owner"),
                "Family": _parse_tier_actions(tier_policy_src, "Family"),
                "Guest": _parse_tier_actions(tier_policy_src, "Guest"),
            },
        },
        "lifecycle": {
            "states": lifecycle_states,
            "valid_transitions": _parse_lifecycle_transitions(lifecycle_src),
            "reason_codes": lifecycle_reasons,
        },
        "energy": {
            "modes": energy_modes,
            "execution_types": execution_types,
            "thresholds": _parse_energy_thresholds(energy_src),
            "decision_reason_codes": energy_reason_codes,
        },
        "storage": {
            "operations": storage_operations,
            "decision_reason_codes": storage_reason_codes,
        },
        "memory": {
            "operations": memory_operations,
            "decision_reason_codes": memory_reason_codes,
        },
    }


def _build_ipc_schema_snapshot() -> dict[str, Any]:
    message_types = [
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
    ]

    descriptor = {
        "schema_version": rust_bridge.IPC_SCHEMA_VERSION,
        "envelope": {
            "required_fields": ["message_type", "timestamp", "correlation_id", "payload"],
            "timestamp_type": "integer_ms",
            "correlation_id_type": "non_empty_string",
            "payload_type": "object",
        },
        "message_types": message_types,
        "max_message_bytes": rust_bridge.MAX_MESSAGE_BYTES,
    }

    encoded = json.dumps(descriptor, sort_keys=True, separators=(",", ":"))
    descriptor["schema_hash_sha256"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return descriptor


def export_contracts() -> tuple[Path, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    authority_path = OUTPUT_DIR / "authority_snapshot.json"
    ipc_path = OUTPUT_DIR / "ipc_schema_v1.json"

    authority_payload = _build_authority_snapshot()
    ipc_payload = _build_ipc_schema_snapshot()

    authority_path.write_text(json.dumps(authority_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ipc_path.write_text(json.dumps(ipc_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return authority_path, ipc_path


def main() -> int:
    export_contracts()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
