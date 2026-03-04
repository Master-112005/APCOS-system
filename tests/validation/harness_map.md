# APCOS RELEASE CONTRACT — DO NOT MODIFY
# Milestone: APCOS-RC1

# APCOS Validation Harness Map

This file is the deterministic index for release-candidate software freeze validation.

## authority
- `os/tests/contract_snapshot_tests.rs`: frozen contract snapshots for lifecycle, memory, energy, storage, identity, and IPC.
- `os/tests/identity_authority_tests.rs`: identity policy authority checks.
- `os/tests/lifecycle_authority_tests.rs`: lifecycle authority transition checks.
- `os/tests/energy_authority_tests.rs`: energy authority gating checks.
- `os/tests/storage_authority_tests.rs`: storage authority permission checks.
- `os/tests/memory_authority_tests.rs`: memory authority transition checks.
- `os/tests/ipc_tests.rs`: IPC message dispatch and loop-prevention checks.

## behavioral
- `tests/behavioral/multi_source_sync/*`: multi-source sync interaction behavior.
- `tests/behavioral/memory_transitions/*`: lifecycle transition behavior under load.
- `tests/behavioral/energy_runtime/*`: runtime adaptation behavior across energy modes.

## calibration
- `tests/validation/fine_tuning/proactive/*`: proactive frequency, repetition, and cooldown calibration.
- `tests/validation/fine_tuning/reasoning/*`: reasoning output bounds and advisory safety.
- `tests/validation/fine_tuning/voice_latency/*`: ASR/TTS latency profiling and cache reuse checks.

## stability
- `tests/stability/wakeword_cycles/*`: repeated wakeword loop stability.
- `tests/stability/sync_burst/*`: sync burst throughput and queue integrity.
- `tests/stability/event_flood/*`: internal event flood stability and deadlock checks.
- `tests/stability/battery_transitions/*`: long-run battery mode transitions under active runtime.
- `tests/stability/extended_runtime/*`: 10k-cycle soak simulation with memory/thread/latency monitoring.

## soak
- `tests/stability/extended_runtime/test_extended_runtime_cycles.py`: long-horizon integrated runtime simulation.
- `tests/stability/extended_runtime/test_memory_growth_stability.py`: memory growth bounds.
- `tests/stability/extended_runtime/test_thread_count_stability.py`: thread count stability.
- `tests/stability/extended_runtime/test_latency_drift_profile.py`: latency drift envelope checks.
