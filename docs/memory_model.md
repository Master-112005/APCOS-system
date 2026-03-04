# Memory Model

## Hybrid Memory

APCOS uses hybrid memory:

- Structured task memory (lifecycle-aware records)
- Semantic memory extensions (vector-oriented context support)

## Lifecycle Principles

- Task transitions are deterministic.
- Invalid transitions are denied by authority checks.
- Archived states are terminal unless explicitly authorized by policy.

## Storage and Memory Authority

- Storage authority decides write permission and retention policy checks.
- Memory authority decides transition permission and target state.
- Python execution layer performs only approved operations.

## Freeze Guarantees

- No direct memory mutation outside approved router execution paths.
- No local bypass of Rust supervision checks.
- Contract structures for decisions remain stable.

