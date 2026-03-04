use apcos_os::energy_manager::{EnergyMode, ExecutionType};
use apcos_os::secure_storage::{
    authorize_storage, parse_storage_operation, StorageDecision, StorageOperation,
};

fn decision_for(
    operation: StorageOperation,
    lifecycle_state: &str,
    energy_mode: EnergyMode,
    execution_type: ExecutionType,
    encryption_metadata_present: bool,
    encryption_key_id: Option<String>,
) -> StorageDecision {
    authorize_storage(
        operation,
        lifecycle_state,
        energy_mode,
        execution_type,
        encryption_metadata_present,
        encryption_key_id,
    )
}

#[test]
fn allowed_write_with_valid_metadata() {
    let decision = decision_for(
        StorageOperation::WriteTask,
        "CREATED",
        EnergyMode::Strategic,
        ExecutionType::BackgroundTask,
        true,
        Some("key-1".to_string()),
    );
    assert!(decision.allowed);
    assert!(decision.reason.is_empty());
    assert!(decision.encryption_verified);
}

#[test]
fn denied_write_when_energy_restricted_for_llm() {
    let decision = decision_for(
        StorageOperation::VectorWrite,
        "ACTIVE",
        EnergyMode::Silent,
        ExecutionType::LLM,
        true,
        Some("key-2".to_string()),
    );
    assert!(!decision.allowed);
    assert_eq!(decision.reason, "LLM_STORAGE_BLOCKED_RESTRICTED_ENERGY");
}

#[test]
fn archival_enforcement_denies_update_on_archived_state() {
    let decision = decision_for(
        StorageOperation::UpdateTask,
        "ARCHIVED",
        EnergyMode::Strategic,
        ExecutionType::BackgroundTask,
        true,
        Some("key-3".to_string()),
    );
    assert!(!decision.allowed);
    assert_eq!(decision.reason, "ARCHIVED_STATE_IMMUTABLE");
    assert!(decision.retention_applied);
}

#[test]
fn encryption_metadata_missing_is_denied() {
    let decision = decision_for(
        StorageOperation::WriteTask,
        "CREATED",
        EnergyMode::Strategic,
        ExecutionType::BackgroundTask,
        false,
        None,
    );
    assert!(!decision.allowed);
    assert_eq!(decision.reason, "ENCRYPTION_METADATA_MISSING");
    assert!(!decision.encryption_verified);
}

#[test]
fn invalid_operation_parsing_is_rejected() {
    assert!(parse_storage_operation("INVALID_OPERATION").is_none());
}
