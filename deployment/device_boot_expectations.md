# APCOS RELEASE CONTRACT - DO NOT MODIFY
# Milestone: APCOS-RC1

## Device Boot Expectations

This document defines firmware-facing startup expectations for APCOS RC1 without changing runtime behavior.

## Boot Authority Chain

Firmware entry chain must preserve:
1. Firmware launch boundary
2. Rust OS authority core startup
3. IPC boundary readiness
4. Python cognitive runtime connection
5. Voice pipeline readiness
6. Cognitive ready state

Runtime mutation authority remains in Python router execution, with all policy authority checks upstream in Rust.

## IPC Startup Lifecycle

Expected lifecycle:
1. Firmware launches Rust OS supervisor process.
2. Rust OS opens JSON-over-stdio IPC boundary.
3. Python runtime bridge connects to the IPC channel.
4. Firmware sends initial energy snapshot.
5. System transitions to ready state after IPC and authority checks are available.

Readiness indicators:
- IPC envelope compatibility: `schema_version = 1`.
- Required envelope fields are present (`message_type`, `timestamp`, `correlation_id`, `payload`).
- Correlation IDs are preserved request-to-response.

## Cognition Start Requirements

Before normal cognition workload:
- Initial energy handshake must be delivered.
- Authority stack (`identity -> lifecycle -> energy -> storage -> memory`) must be available.
- IPC boundary must be live and schema-compatible.

Reasoning and proactive execution are gated by energy authority decisions and must not run as ungated startup behavior.

## Voice Pipeline Readiness

Voice readiness expectations:
- Wakeword requirement remains active.
- Voice path may remain available in silent mode.
- Heavy cognition remains energy-gated during silent mode.

## Contract Scope

This document is descriptive only and intentionally excludes:
- firmware source code
- MCU scheduling implementation
- hardware driver implementation details
