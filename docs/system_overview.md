# System Overview

## Mission

APCOS is an on-device supervised cognitive runtime for persistent task intelligence with strict authority boundaries.

## Subsystems

- Voice interface engine
- Identity and access-control layer
- Cognitive core engine
- Memory and task lifecycle engine
- Proactive behavioral engine
- Compute decision controller
- Energy and resource manager

## High-Level Execution

```text
Input Adapter -> Parser -> IPC Supervision -> Router -> Memory
                               |
                        Rust Authority Stack
```

## Authority Stack

`Identity -> Lifecycle -> Energy -> Storage -> Memory`

This stack is frozen for release-candidate behavior.

