# Cognitive Engine

## Design

APCOS uses a two-tier cognitive approach:

1. Symbolic intent parsing for deterministic command paths.
2. Advisory reasoning for strategy and explanation paths.

## Deterministic Path

- Intent parser maps input to structured intent.
- Router validates entities and confidence.
- Router executes mutations only on approved actions.
- Router emits command results and audit events.

## Advisory Path

- Reasoning engine generates strategy output.
- Output is bounded and safety-filtered.
- Strategy output is advisory-only and non-executable.

## Freeze Guarantees

- No new mutation paths may be introduced outside router.
- Reasoning output contract remains stable.
- Reasoning must not produce executable mutation instructions.

