# APCOS RELEASE CONTRACT - DO NOT MODIFY
# Milestone: APCOS-RC1

## Energy Handshake Contract

This contract defines firmware-to-APCOS energy signaling expectations for RC1 device entry.

## Initial Energy Handshake

Before cognition-ready state, firmware must provide an initial energy snapshot through the IPC event/validation path containing:
- `battery_percent` (integer-like value, 0-100 range)
- thermal state signal (temperature-derived or threshold-derived value compatible with runtime energy evaluation)

The initial snapshot is a startup prerequisite for safe cognition gating behavior.

## Energy Update Lifecycle

Expected lifecycle:
1. Firmware sends energy updates through IPC-compatible envelopes.
2. Rust energy authority evaluates mode and execution viability.
3. Rust returns deterministic allow/deny outcomes for execution classes.
4. Python runtime adapts to decisions and must not override denials.

Energy mode vocabulary (frozen):
- `Strategic`
- `Reduced`
- `Silent`

## Silent-Mode Behavior Expectations

When mode is `Silent`:
- LLM execution is blocked.
- Proactive execution is suppressed.
- Background task execution is blocked.
- Voice path and critical reminder path remain allowed.

## Contract Boundaries

This contract intentionally does not define:
- battery voltage curves
- firmware battery-driver logic
- thermal driver implementation
- hardware scheduling policy
