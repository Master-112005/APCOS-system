# Energy Management

## Energy Modes

- Strategic
- Reduced
- Silent

## Execution Supervision

Energy authority classifies execution types and returns allow/deny decisions.

Typical policy intent:

- Strategic: full runtime execution
- Reduced: downgraded heavy compute
- Silent: deny non-critical heavy cognition

## Runtime Adaptation

- Python runtime adapts to energy decisions.
- Denials are respected and not overridden locally.
- Voice and critical flows remain available under strict policy limits.

## Freeze Guarantees

- Energy mode and execution type contracts are snapshot-tested.
- No authority logic drift without explicit contract versioning.

