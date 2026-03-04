# API Specification

## IPC Protocol (v1)

Schema version: `1`

Envelope:

```json
{
  "message_type": "EVENT | STATE_UPDATE | AUTH_REQUEST | AUTH_RESULT | TRANSITION_VALIDATE | TRANSITION_RESULT | ENERGY_VALIDATE | ENERGY_RESULT | STORAGE_VALIDATE | STORAGE_RESULT | MEMORY_VALIDATE | MEMORY_RESULT",
  "timestamp": 1700000000000,
  "correlation_id": "string",
  "payload": {}
}
```

## Contract Rules

- Correlation id is required for loop suppression and traceability.
- Unknown message types are ignored or denied by parser policy.
- Validation request paths are non-mutating and fail-closed.

## Command Router Contract

`CommandRouter.route(intent_object) -> CommandResult`

`CommandResult` fields:

- `status`
- `action`
- `audit_id`
- `message_key`
- `metadata`
- `error_code` (optional)
- `challenge_payload` (optional)

## Reasoning Output Contract

`StructuredReasoningOutput` fields:

- `summary`
- `strategy_steps`
- `safe_to_present`
- `blocked_reason` (optional)

