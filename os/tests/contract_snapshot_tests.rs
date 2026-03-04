#[path = "../src/ipc.rs"]
mod ipc;

#[path = "../src/runtime/memory_authority.rs"]
mod memory_authority_snapshot;

use apcos_os::energy_manager::{
    authorize_execution, determine_mode, parse_execution_type, EnergyMode, ExecutionType,
};
use apcos_os::identity::tier_policy::{is_allowed, parse_tier, Tier};
use apcos_os::runtime::lifecycle::{
    is_valid_transition, parse_task_state, validate_transition, validate_transition_from_str,
    LifecycleResult, TaskState,
};
use apcos_os::secure_storage::{
    authorize_storage, parse_energy_mode, parse_storage_operation, StorageDecision, StorageOperation,
};
use memory_authority_snapshot::{
    determine_memory_transition, parse_memory_operation, MemoryDecision, MemoryMetadataFlags,
    MemoryOperation,
};
use serde_json::{json, to_string, to_value, Value};
use std::collections::BTreeSet;

#[test]
fn test_energy_contract_snapshot() {
    assert_eq!(determine_mode(60), EnergyMode::Strategic);
    assert_eq!(determine_mode(30), EnergyMode::Reduced);
    assert_eq!(determine_mode(10), EnergyMode::Silent);

    let mode_variants = vec![EnergyMode::Strategic, EnergyMode::Reduced, EnergyMode::Silent];
    let serialized_modes: Vec<String> = mode_variants
        .iter()
        .filter_map(|mode| to_string(mode).ok())
        .collect();
    assert_eq!(
        serialized_modes,
        vec![
            "\"Strategic\"".to_string(),
            "\"Reduced\"".to_string(),
            "\"Silent\"".to_string(),
        ]
    );

    let execution_variants = vec![
        ExecutionType::LLM,
        ExecutionType::Proactive,
        ExecutionType::BackgroundTask,
        ExecutionType::CriticalReminder,
        ExecutionType::Voice,
    ];
    let serialized_execution_types: Vec<String> = execution_variants
        .iter()
        .filter_map(|value| to_string(value).ok())
        .collect();
    assert_eq!(
        serialized_execution_types,
        vec![
            "\"LLM\"".to_string(),
            "\"Proactive\"".to_string(),
            "\"BackgroundTask\"".to_string(),
            "\"CriticalReminder\"".to_string(),
            "\"Voice\"".to_string(),
        ]
    );

    assert_eq!(parse_execution_type("LLM"), Some(ExecutionType::LLM));
    assert_eq!(parse_execution_type("PROACTIVE"), Some(ExecutionType::Proactive));
    assert_eq!(
        parse_execution_type("BACKGROUND_TASK"),
        Some(ExecutionType::BackgroundTask)
    );
    assert_eq!(
        parse_execution_type("CRITICAL_REMINDER"),
        Some(ExecutionType::CriticalReminder)
    );
    assert_eq!(parse_execution_type("VOICE"), Some(ExecutionType::Voice));
    assert_eq!(parse_execution_type("UNKNOWN"), None);

    let decision = authorize_execution(&EnergyMode::Reduced, ExecutionType::LLM);
    assert_eq!(
        to_value(&decision).ok(),
        Some(json!({"allowed": true, "reason": "LLM_DOWNGRADED_REDUCED"}))
    );
}

#[test]
fn test_memory_contract_snapshot() {
    let operations = vec![
        "PROMOTE_TO_ACTIVE",
        "DEMOTE_TO_DORMANT",
        "ARCHIVE_ITEM",
        "FINALIZE_ARCHIVE",
        "RETENTION_TRIGGER",
        "VECTOR_TIER_SHIFT",
    ];
    let parsed_ops: Vec<MemoryOperation> = operations
        .iter()
        .filter_map(|value| parse_memory_operation(value))
        .collect();
    let serialized_ops: Vec<String> = parsed_ops
        .iter()
        .filter_map(|operation| to_string(operation).ok())
        .collect();
    assert_eq!(
        serialized_ops,
        vec![
            "\"PROMOTE_TO_ACTIVE\"".to_string(),
            "\"DEMOTE_TO_DORMANT\"".to_string(),
            "\"ARCHIVE_ITEM\"".to_string(),
            "\"FINALIZE_ARCHIVE\"".to_string(),
            "\"RETENTION_TRIGGER\"".to_string(),
            "\"VECTOR_TIER_SHIFT\"".to_string(),
        ]
    );
    assert_eq!(parse_memory_operation("UNKNOWN"), None);

    let allowed = determine_memory_transition(
        "ACTIVE",
        EnergyMode::Strategic,
        true,
        MemoryOperation::ArchiveItem,
        MemoryMetadataFlags {
            retention_due: true,
            ..MemoryMetadataFlags::default()
        },
    );
    assert_eq!(
        to_value(&allowed).ok(),
        Some(json!({
            "allowed": true,
            "reason": "",
            "target_state": "ARCHIVED",
            "retention_applied": true,
            "tier_changed": true
        }))
    );

    let denied = determine_memory_transition(
        "ACTIVE",
        EnergyMode::Silent,
        true,
        MemoryOperation::DemoteToDormant,
        MemoryMetadataFlags::default(),
    );
    assert_eq!(
        to_value(&denied).ok(),
        Some(json!({
            "allowed": false,
            "reason": "SILENT_MODE_MEMORY_RESTRICTED",
            "target_state": Value::Null,
            "retention_applied": false,
            "tier_changed": false
        }))
    );

    let field_lock = MemoryDecision {
        allowed: false,
        reason: "LOCKED".to_string(),
        target_state: None,
        retention_applied: false,
        tier_changed: false,
    };
    assert_eq!(
        to_value(&field_lock).ok(),
        Some(json!({
            "allowed": false,
            "reason": "LOCKED",
            "target_state": Value::Null,
            "retention_applied": false,
            "tier_changed": false
        }))
    );
}

#[test]
fn test_lifecycle_contract_snapshot() {
    let parsed_states: Vec<String> = ["pending", "completed", "archived"]
        .iter()
        .filter_map(|value| parse_task_state(value))
        .map(|state| format!("{state:?}"))
        .collect();
    assert_eq!(
        parsed_states,
        vec![
            "Pending".to_string(),
            "Completed".to_string(),
            "Archived".to_string()
        ]
    );
    assert_eq!(parse_task_state("unknown"), None);

    assert!(is_valid_transition(TaskState::Pending, TaskState::Completed));
    assert!(is_valid_transition(TaskState::Pending, TaskState::Archived));
    assert!(is_valid_transition(TaskState::Completed, TaskState::Archived));
    assert!(!is_valid_transition(TaskState::Completed, TaskState::Pending));
    assert!(!is_valid_transition(TaskState::Archived, TaskState::Pending));

    let archived_terminal = validate_transition(TaskState::Archived, TaskState::Completed);
    assert_eq!(
        archived_terminal,
        LifecycleResult {
            allowed: false,
            reason: Some("ARCHIVED_TERMINAL".to_string()),
        }
    );

    let unknown = validate_transition_from_str("Pending", "Unknown");
    assert_eq!(
        unknown,
        LifecycleResult {
            allowed: false,
            reason: Some("UNKNOWN_STATE".to_string()),
        }
    );
}

#[test]
fn test_storage_contract_snapshot() {
    let parsed_operations: Vec<StorageOperation> = [
        "WRITE_TASK",
        "UPDATE_TASK",
        "ARCHIVE_TASK",
        "DELETE_TASK",
        "VECTOR_WRITE",
        "VECTOR_DELETE",
    ]
    .iter()
    .filter_map(|value| parse_storage_operation(value))
    .collect();
    let serialized_operations: Vec<String> = parsed_operations
        .iter()
        .filter_map(|operation| to_string(operation).ok())
        .collect();
    assert_eq!(
        serialized_operations,
        vec![
            "\"WRITE_TASK\"".to_string(),
            "\"UPDATE_TASK\"".to_string(),
            "\"ARCHIVE_TASK\"".to_string(),
            "\"DELETE_TASK\"".to_string(),
            "\"VECTOR_WRITE\"".to_string(),
            "\"VECTOR_DELETE\"".to_string(),
        ]
    );
    assert_eq!(parse_storage_operation("UNKNOWN"), None);
    assert_eq!(parse_energy_mode("STRATEGIC"), Some(EnergyMode::Strategic));
    assert_eq!(parse_energy_mode("REDUCED"), Some(EnergyMode::Reduced));
    assert_eq!(parse_energy_mode("SILENT"), Some(EnergyMode::Silent));
    assert_eq!(parse_energy_mode("UNKNOWN"), None);

    let denied = authorize_storage(
        StorageOperation::WriteTask,
        "CREATED",
        EnergyMode::Strategic,
        ExecutionType::BackgroundTask,
        false,
        None,
    );
    assert_eq!(
        to_value(&denied).ok(),
        Some(json!({
            "allowed": false,
            "reason": "ENCRYPTION_METADATA_MISSING",
            "retention_applied": false,
            "encryption_verified": false
        }))
    );

    let field_lock = StorageDecision {
        allowed: true,
        reason: String::new(),
        retention_applied: true,
        encryption_verified: true,
    };
    assert_eq!(
        to_value(&field_lock).ok(),
        Some(json!({
            "allowed": true,
            "reason": "",
            "retention_applied": true,
            "encryption_verified": true
        }))
    );
}

#[test]
fn test_identity_contract_snapshot() {
    assert_eq!(parse_tier("Owner"), Some(Tier::Owner));
    assert_eq!(parse_tier("Family"), Some(Tier::Family));
    assert_eq!(parse_tier("Guest"), Some(Tier::Guest));
    assert_eq!(parse_tier("Unknown"), None);

    assert!(is_allowed(&Tier::Owner, "CREATE_TASK"));
    assert!(is_allowed(&Tier::Owner, "CANCEL_TASK"));
    assert!(is_allowed(&Tier::Family, "CREATE_TASK"));
    assert!(!is_allowed(&Tier::Family, "CANCEL_TASK"));
    assert!(!is_allowed(&Tier::Guest, "STRATEGY"));
}

#[test]
fn test_ipc_contract_snapshot() {
    assert_eq!(ipc::IPC_SCHEMA_VERSION, 1);

    let message_types = vec![
        ipc::MessageType::Event,
        ipc::MessageType::StateUpdate,
        ipc::MessageType::AuthRequest,
        ipc::MessageType::AuthResult,
        ipc::MessageType::TransitionValidate,
        ipc::MessageType::TransitionResult,
        ipc::MessageType::EnergyValidate,
        ipc::MessageType::EnergyResult,
        ipc::MessageType::StorageValidate,
        ipc::MessageType::StorageResult,
        ipc::MessageType::MemoryValidate,
        ipc::MessageType::MemoryResult,
    ];
    let serialized_message_types: Vec<String> = message_types
        .iter()
        .filter_map(|message_type| to_string(message_type).ok())
        .collect();
    assert_eq!(
        serialized_message_types,
        vec![
            "\"EVENT\"".to_string(),
            "\"STATE_UPDATE\"".to_string(),
            "\"AUTH_REQUEST\"".to_string(),
            "\"AUTH_RESULT\"".to_string(),
            "\"TRANSITION_VALIDATE\"".to_string(),
            "\"TRANSITION_RESULT\"".to_string(),
            "\"ENERGY_VALIDATE\"".to_string(),
            "\"ENERGY_RESULT\"".to_string(),
            "\"STORAGE_VALIDATE\"".to_string(),
            "\"STORAGE_RESULT\"".to_string(),
            "\"MEMORY_VALIDATE\"".to_string(),
            "\"MEMORY_RESULT\"".to_string(),
        ]
    );

    let envelope = ipc::build_event_envelope("BatteryLow", json!({"percent": 15}), "cid-lock");
    let value = to_value(envelope).ok();
    let key_set = value.and_then(|payload| {
        payload.as_object().map(|map| {
            map.keys()
                .map(|key| key.to_string())
                .collect::<BTreeSet<String>>()
        })
    });
    assert_eq!(
        key_set,
        Some(
            ["message_type", "timestamp", "correlation_id", "payload"]
                .iter()
                .map(|key| key.to_string())
                .collect::<BTreeSet<String>>()
        )
    );
}
