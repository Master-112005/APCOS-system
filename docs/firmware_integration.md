# APCOS Firmware Integration Guide (RC1 Freeze)

## Release Boundary
- Runtime milestone: `APCOS-RC1`
- Contract artifacts:
  - `deployment/contracts/authority_snapshot.json`
  - `deployment/contracts/ipc_schema_v1.json`
  - `models/model_registry.json`
  - `tests/validation/harness_map.md`
- These artifacts are frozen for RC1 and treated as device integration law.

## Authority Enforcement Boundaries
- Identity authority: Rust OS identity policy validates tier/action access.
- Lifecycle authority: Rust validates transition legality before router execution.
- Energy authority: Rust validates execution class viability by mode.
- Storage authority: Rust validates write/retention/encryption metadata policy.
- Memory authority: Rust validates memory transition policy.
- Router remains the exclusive mutation executor on Python side.

## IPC Schema (v1) Summary
- Schema version: `1`
- Envelope keys (required):
  - `message_type`
  - `timestamp`
  - `correlation_id`
  - `payload`
- Message classes:
  - `EVENT`, `STATE_UPDATE`
  - `AUTH_REQUEST`, `AUTH_RESULT`
  - `TRANSITION_VALIDATE`, `TRANSITION_RESULT`
  - `ENERGY_VALIDATE`, `ENERGY_RESULT`
  - `STORAGE_VALIDATE`, `STORAGE_RESULT`
  - `MEMORY_VALIDATE`, `MEMORY_RESULT`
- Correlation IDs are required and must round-trip unchanged in request/response pairs.

## Energy Authority Behavior
- Modes:
  - `Strategic`
  - `Reduced`
  - `Silent`
- Execution gating:
  - Strategic: all execution classes allowed.
  - Reduced: background tasks restricted; LLM can be downgraded.
  - Silent: heavy cognition denied; critical reminder and voice paths allowed.
- Python runtime adapts to decisions and must not override Rust denials.

## Memory Authority Transition Behavior
- Memory operations are validated by Rust before Python transition execution.
- Transition decisions are deterministic and fail-closed.
- Transition authorization requires storage permission signal integration.
- Archived reactivation remains denied unless explicitly allowed by metadata policy.

## Device Boot Expectations
- Boot sequence should initialize contracts first:
  - Validate contract artifact presence under `deployment/contracts/`.
  - Validate model manifest presence at `models/model_registry.json`.
  - Start Rust OS supervisor runtime and IPC boundary.
  - Start Python cognitive runtime as execution client.
- Firmware should treat missing or mismatched contract files as startup failure.
- Firmware should not assume mutable schema or authority behavior during RC1.
