# APCOS RELEASE CONTRACT - DO NOT MODIFY
# Milestone: APCOS-RC1

## Hardware Runtime Expectations

This document defines what the APCOS RC1 runtime expects from firmware and hardware-facing layers.

## Energy Reporting Expectations

- Battery percentage must be provided as integer-like value in [0, 100].
- Thermal health must be represented in a deterministic signal path (numeric temperature and/or threshold flag equivalent).
- Energy updates should be periodic and bounded; avoid burst-only reporting.
- Initial energy snapshot is expected before regular cognition workload is accepted.

## Voice Pipeline Expectations

- Wakeword trigger is required before normal voice command flow.
- Audio should be delivered through firmware buffer boundaries, not direct cognition mutation paths.
- Firmware must not run ASR decision logic that bypasses APCOS authority layers.
- Voice interaction remains available under silent mode while heavy cognition stays energy-gated.

## Sync and External State Expectations

- External state and event traffic must enter via connector/sync IPC envelopes.
- Sync payloads are advisory inputs; they are not direct mutation commands.
- Correlation identifiers must be preserved across request-response boundaries.

## Authority Enforcement Expectations

Firmware integration must preserve this frozen authority order:
1. identity
2. lifecycle
3. energy
4. storage
5. memory

Rules:
- Do not bypass Rust authority decisions.
- Do not invoke Python mutation paths outside router execution boundary.
- Do not alter IPC schema fields or envelope shape.

## Boot and Readiness Expectations

- Firmware should treat missing frozen contracts as startup failure condition.
- Runtime compatibility should be checked against:
  - `deployment/contracts/authority_snapshot.json`
  - `deployment/contracts/ipc_schema_v1.json`
  - `deployment/contracts/device_runtime_profile.json`
  - `models/model_registry.json`

## Out of Scope

This document does not define:
- hardware pin mappings
- DSP firmware algorithms
- driver APIs or low-level RTOS implementation details
