# APCOS

Adaptive Personal Cognitive Operating System (APCOS) is a supervised cognitive runtime designed for device deployment.

This repository is in release-candidate freeze mode.

## Freeze Scope

- Authority stack is fixed: `Identity -> Lifecycle -> Energy -> Storage -> Memory`
- Router remains the exclusive Python mutation path
- Rust OS layer remains the supervisory authority layer
- IPC schema is versioned and contract-locked

## Core Runtime Flow

1. Input enters via CLI or voice adapters.
2. Python parses intent and builds structured requests.
3. Rust supervision validates identity, lifecycle, energy, storage, and memory decisions.
4. Python executes only approved actions.
5. Router emits structured command results and audits.

## IPC Protocol Summary

- IPC transport: JSON over stdio
- Envelope keys: `message_type`, `timestamp`, `correlation_id`, `payload`
- Schema version: `IPC_SCHEMA_VERSION = 1`
- Message types are fixed and snapshot-tested.

## Energy Model Summary

- `Strategic`: full execution
- `Reduced`: downgraded compute
- `Silent`: heavy cognition denied, critical paths only

## Identity Tiers Summary

- `Owner`: full command set
- `Family`: constrained command set
- `Guest`: strategy/advisory-only paths by policy

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
```

Rust validation:

```bash
cd os
cargo build
cargo test
cargo clippy -- -D warnings
```

## Repository Structure

- `os/`: Rust supervisory authority layer
- `core/`: deterministic cognitive and behavior runtime
- `services/`: adapters and service-level glue
- `voice/`: voice runtime and model lifecycle adapters
- `tests/`: security, behavioral, stability, and soak validation
- `docs/`: frozen engineering documentation
- `models/model_registry.json`: device model manifest


# APCOS Roadmap (Post-Freeze)

## Current State

- Release candidate software freeze active
- Authority contracts and IPC protocol locked
- Stability and soak validation suites operational

## Near-Term Milestones

1. RC validation sign-off
2. Device image packaging against frozen model manifest
3. Hardware integration test pass against frozen contracts
4. Firmware adapter conformance tests against IPC v1

## Change Governance After Freeze

- Any authority contract change requires version bump and migration notes.
- Any IPC schema change requires protocol version bump.
- Mutation-path changes require security and regression recertification.

## Out-of-Scope During Freeze

- New runtime services
- New IPC message classes
- Authority policy redesign
- Router mutation redesign

# APCOS Security Model (Frozen RC)

## Security Principles

- Fail-closed authority decisions
- Least privilege by identity tier
- Router-exclusive mutation execution
- Deterministic lifecycle and memory transitions
- No silent fallback on supervision failure

## Access Control

Identity is validated before mutation paths.

- `Owner`
- `Family`
- `Guest`

Tier policy is authority-defined and contract-tested.

## IPC Safety

- Schema-validated envelopes only
- Correlation-id loop suppression
- Unknown and malformed messages ignored or denied
- No mutation commands accepted through IPC

## Mutation Integrity

- Import and call-path checks enforce router exclusivity
- Mutation coverage tests verify audits on mutation paths
- Strategy/reasoning remains advisory-only

## Energy and Runtime Safety

- Energy authority gates execution classes
- Heavy cognition is denied or downgraded by policy
- Runtime governor and hardware signals remain supervisory

## Data and Storage Safety

- Storage authority validates mutation permission and retention rules
- Memory authority validates transition decisions
- Encryption metadata is validated in authority path

## Prohibited Patterns

- Direct lifecycle mutation outside router
- Direct task-store mutation outside memory layer
- Cross-layer bypasses around authority chain
- Unversioned schema contract changes

# APCOS Architecture (Frozen RC)

## System Positioning

APCOS is a supervised cognitive runtime with split responsibilities:

- Rust OS layer: authority decisions and supervision
- Python runtime: intent interpretation, orchestration, and approved execution

## Authority Stack

The authority chain is fixed:

`Identity -> Lifecycle -> Energy -> Storage -> Memory`

All authority layers are fail-closed.

## Mutation Boundary

- Router is the exclusive mutation boundary in Python.
- No module outside router may perform lifecycle or task-store mutation directly.
- IPC and adapters are envelope-only and non-mutating.

## IPC Contract

- Transport: JSON lines over stdio
- Frozen envelope:
  - `message_type`
  - `timestamp`
  - `correlation_id`
  - `payload`
- Frozen schema version: `1`

## Cognitive Interfaces

Frozen interfaces include:

- `CommandRouter.route(intent_object) -> CommandResult`
- Reasoning output contract:
  - `summary`
  - `strategy_steps`
  - `safe_to_present`
  - `blocked_reason`

## Energy Supervision

Energy authority is in Rust and supervises execution class viability:

- `Strategic`
- `Reduced`
- `Silent`

Python adapts to decisions and cannot override denials.

## Stability and Certification

Validation is organized under:

- `tests/security`
- `tests/behavioral`
- `tests/runtime`
- `tests/stability`
- `tests/validation`

Harness index: `tests/validation/harness_map.md`.

