# APCOS RELEASE CONTRACT - DO NOT MODIFY
# Milestone: APCOS-RC1

## Boot Sequence Contract

This document defines startup expectations for firmware integration against the frozen APCOS RC1 runtime.

## Boot Stages

1. Stage 1 - Rust OS Core Startup
- Start Rust supervisor runtime.
- Load frozen authority contracts.
- Initialize deterministic event/validation boundaries.

2. Stage 2 - IPC Bridge Ready
- Open JSON-over-stdio IPC boundary.
- Confirm schema version compatibility (`schema_version = 1`).
- Accept only envelope-conformant messages.

3. Stage 3 - Python Runtime Launch
- Launch Python cognitive executor.
- Bind Python bridge to existing Rust IPC channel.
- Keep router as the only mutation executor.

4. Stage 4 - Voice Pipeline Ready
- Initialize wakeword and voice adapters.
- Keep lazy model lifecycle behavior active.
- Permit voice path in silent energy mode while heavy cognition remains gated.

5. Stage 5 - Cognitive Ready State
- Accept external events and sync envelopes.
- Allow cognition requests only after authority gates return allowed decisions.

## IPC Lifecycle

1. Firmware launches Rust OS supervisor.
2. Rust supervisor opens stdio JSON IPC boundary.
3. Python runtime connects as execution client.
4. Firmware sends initial energy snapshot into runtime integration path.
5. Runtime enters operational state when IPC and authority boundaries are ready.

## Energy Initialization Expectations

- APCOS expects initial battery/energy state before normal cognition traffic.
- Energy authority controls execution viability before heavy cognition paths.
- Python runtime adapts to authority decisions and must not override denials.

## Readiness Signals

APCOS runtime should be considered ready for firmware traffic when all are true:
- IPC schema check succeeded (`deployment/contracts/ipc_schema_v1.json`).
- Authority snapshot loaded (`deployment/contracts/authority_snapshot.json`).
- Runtime profile recognized (`deployment/contracts/device_runtime_profile.json`).
- Model manifest present (`models/model_registry.json`).

## Out of Scope

This contract intentionally excludes:
- firmware implementation code
- MCU scheduling logic
- device driver instructions
