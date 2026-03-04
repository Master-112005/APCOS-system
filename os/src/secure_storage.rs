//! Stage 15 storage authority policy for kernel-level validation.
//!
//! This module intentionally performs no filesystem I/O. Python remains the
//! physical storage executor; Rust is the authority for storage mutation
//! permission, retention enforcement, and encryption metadata validation.

use crate::energy_manager::{EnergyMode, ExecutionType};
use serde::{Deserialize, Serialize};
use thiserror::Error;

/// Semantic storage operations requested by Python memory clients.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum StorageOperation {
    WriteTask,
    UpdateTask,
    ArchiveTask,
    DeleteTask,
    VectorWrite,
    VectorDelete,
}

/// Structured decision returned by Rust storage authority.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct StorageDecision {
    pub allowed: bool,
    pub reason: String,
    pub retention_applied: bool,
    pub encryption_verified: bool,
}

impl StorageDecision {
    fn allow(retention_applied: bool, encryption_verified: bool) -> Self {
        Self {
            allowed: true,
            reason: String::new(),
            retention_applied,
            encryption_verified,
        }
    }

    fn deny(reason: &str, retention_applied: bool, encryption_verified: bool) -> Self {
        Self {
            allowed: false,
            reason: reason.to_string(),
            retention_applied,
            encryption_verified,
        }
    }
}

/// Input contract for deterministic storage policy evaluation.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct StoragePolicyInput {
    pub operation: StorageOperation,
    pub lifecycle_state: String,
    pub energy_mode: EnergyMode,
    pub execution_type: ExecutionType,
    pub encryption_metadata_present: bool,
    pub encryption_key_id: Option<String>,
}

/// Parse operation string from IPC payload into strongly typed operation.
pub fn parse_storage_operation(value: &str) -> Option<StorageOperation> {
    match value.trim().to_ascii_uppercase().as_str() {
        "WRITE_TASK" => Some(StorageOperation::WriteTask),
        "UPDATE_TASK" => Some(StorageOperation::UpdateTask),
        "ARCHIVE_TASK" => Some(StorageOperation::ArchiveTask),
        "DELETE_TASK" => Some(StorageOperation::DeleteTask),
        "VECTOR_WRITE" => Some(StorageOperation::VectorWrite),
        "VECTOR_DELETE" => Some(StorageOperation::VectorDelete),
        _ => None,
    }
}

/// Parse serialized energy mode from IPC payload.
pub fn parse_energy_mode(value: &str) -> Option<EnergyMode> {
    match value.trim().to_ascii_uppercase().as_str() {
        "STRATEGIC" => Some(EnergyMode::Strategic),
        "REDUCED" => Some(EnergyMode::Reduced),
        "SILENT" => Some(EnergyMode::Silent),
        _ => None,
    }
}

/// Authorize storage mutation using deterministic policy checks only.
pub fn determine_storage_policy(input: &StoragePolicyInput) -> StorageDecision {
    let key_present = input
        .encryption_key_id
        .as_ref()
        .is_some_and(|value| !value.trim().is_empty());
    let encryption_verified = input.encryption_metadata_present && key_present;
    if !encryption_verified {
        return StorageDecision::deny("ENCRYPTION_METADATA_MISSING", false, false);
    }

    // Hard retention boundary: task deletion remains prohibited at policy layer.
    if matches!(input.operation, StorageOperation::DeleteTask) {
        return StorageDecision::deny("RETENTION_DELETE_DENIED", true, true);
    }

    // Archived tasks are immutable for update-style writes.
    if is_archived_state(input.lifecycle_state.as_str())
        && matches!(
            input.operation,
            StorageOperation::WriteTask
                | StorageOperation::UpdateTask
                | StorageOperation::VectorWrite
                | StorageOperation::VectorDelete
        )
    {
        return StorageDecision::deny("ARCHIVED_STATE_IMMUTABLE", true, true);
    }

    // Restricted energy modes cannot accept LLM-originated storage writes.
    let restricted_energy = matches!(input.energy_mode, EnergyMode::Reduced | EnergyMode::Silent);
    if restricted_energy
        && matches!(input.execution_type, ExecutionType::LLM)
        && is_mutating_operation(&input.operation)
    {
        return StorageDecision::deny("LLM_STORAGE_BLOCKED_RESTRICTED_ENERGY", false, true);
    }

    let retention_applied = matches!(input.operation, StorageOperation::ArchiveTask);
    StorageDecision::allow(retention_applied, true)
}

/// Convenience entry point with normalized primitive inputs.
pub fn authorize_storage(
    operation: StorageOperation,
    lifecycle_state: &str,
    energy_mode: EnergyMode,
    execution_type: ExecutionType,
    encryption_metadata_present: bool,
    encryption_key_id: Option<String>,
) -> StorageDecision {
    let input = StoragePolicyInput {
        operation,
        lifecycle_state: lifecycle_state.to_string(),
        energy_mode,
        execution_type,
        encryption_metadata_present,
        encryption_key_id,
    };
    determine_storage_policy(&input)
}

fn is_archived_state(state: &str) -> bool {
    state.trim().eq_ignore_ascii_case("ARCHIVED")
}

fn is_mutating_operation(operation: &StorageOperation) -> bool {
    matches!(
        operation,
        StorageOperation::WriteTask
            | StorageOperation::UpdateTask
            | StorageOperation::ArchiveTask
            | StorageOperation::DeleteTask
            | StorageOperation::VectorWrite
            | StorageOperation::VectorDelete
    )
}

/// Compatibility wrapper retained for Stage 10 bootstrap probes.
///
/// This no-op container intentionally performs no filesystem I/O and no
/// cryptography in Stage 15.
#[derive(Clone, Debug, Default)]
pub struct SecureStorage;

#[derive(Debug, Error)]
pub enum SecureStorageError {
    #[error("secure storage operation unavailable")]
    Unavailable,
}

impl SecureStorage {
    /// Create no-op secure storage container.
    pub fn with_generated_key() -> Self {
        Self
    }

    /// Compatibility passthrough for bootstrap probes.
    pub fn encrypt(&self, plaintext: &[u8], _aad: &[u8]) -> Result<Vec<u8>, SecureStorageError> {
        Ok(plaintext.to_vec())
    }

    /// Compatibility passthrough for bootstrap probes.
    pub fn decrypt(&self, encrypted: &[u8], _aad: &[u8]) -> Result<Vec<u8>, SecureStorageError> {
        Ok(encrypted.to_vec())
    }
}

#[cfg(test)]
mod tests {
    use super::{
        authorize_storage, parse_energy_mode, parse_storage_operation, StorageOperation,
    };
    use crate::energy_manager::{EnergyMode, ExecutionType};

    #[test]
    fn parse_operation_handles_known_and_unknown_values() {
        assert_eq!(
            parse_storage_operation("WRITE_TASK"),
            Some(StorageOperation::WriteTask)
        );
        assert!(parse_storage_operation("UNKNOWN").is_none());
    }

    #[test]
    fn parse_energy_mode_handles_known_and_unknown_values() {
        assert_eq!(parse_energy_mode("silent"), Some(EnergyMode::Silent));
        assert!(parse_energy_mode("invalid").is_none());
    }

    #[test]
    fn policy_denies_missing_encryption_metadata() {
        let decision = authorize_storage(
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
}
