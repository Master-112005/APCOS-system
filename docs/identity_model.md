# Identity Model

## Identity Scope

Identity is enforced before mutation execution.

## Tiers

- Owner
- Family
- Guest

Tier policies are authority-defined and contract-tested.

## Enforcement Model

- Python builds authorization requests.
- Rust identity authority returns structured allow/deny decisions.
- Denied actions do not reach mutation execution.

## Freeze Guarantees

- Tier enums and policy behavior are contract-locked.
- Identity checks remain deterministic and fail-closed.
- No identity bypass path is permitted in adapters or IPC.

