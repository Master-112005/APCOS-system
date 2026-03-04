# Changelog

All notable changes are tracked here.

## [1.0.0-rc.1] - 2026-02-21

### Added

- Full authority stack supervision in Rust:
  - Identity authority
  - Lifecycle authority
  - Energy authority
  - Storage authority
  - Memory authority
- IPC supervision bridge with schema-validated envelopes and correlation handling
- Interaction, identity, voice, runtime governance, and hardware abstraction layers
- Security, behavioral, runtime, load, stability, and soak validation suites
- Freeze contract snapshot tests for authority and IPC schema

### Stabilized

- Router-exclusive mutation boundary enforcement
- Advisory-only reasoning behavior and bounded outputs
- Voice runtime caching and latency profiling
- Long-run stability harnesses (wakeword, sync burst, event flood, battery transitions, extended runtime)

### Notes

- Release-candidate freeze active.
- Contract changes require explicit version bump and migration notes.

