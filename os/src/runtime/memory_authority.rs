//! Stage 16 memory transition authority policy.
//!
//! This module is deterministic and side-effect free. It performs no
//! filesystem operations and emits no events.
#![allow(dead_code)]

use apcos_os::energy_manager::EnergyMode;
use serde::{Deserialize, Serialize};

/// Semantic memory operations requested by Python memory executors.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum MemoryOperation {
    PromoteToActive,
    DemoteToDormant,
    ArchiveItem,
    FinalizeArchive,
    RetentionTrigger,
    VectorTierShift,
}

/// Metadata hints that influence transition policy.
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct MemoryMetadataFlags {
    #[serde(default)]
    pub critical_reminder: bool,
    #[serde(default)]
    pub allow_archived_reactivation: bool,
    #[serde(default)]
    pub retention_due: bool,
}

/// Structured memory authority decision.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct MemoryDecision {
    pub allowed: bool,
    pub reason: String,
    pub target_state: Option<String>,
    pub retention_applied: bool,
    pub tier_changed: bool,
}

impl MemoryDecision {
    fn allow(target_state: Option<String>, retention_applied: bool, tier_changed: bool) -> Self {
        Self {
            allowed: true,
            reason: String::new(),
            target_state,
            retention_applied,
            tier_changed,
        }
    }

    fn deny(reason: &str, target_state: Option<String>, retention_applied: bool, tier_changed: bool) -> Self {
        Self {
            allowed: false,
            reason: reason.to_string(),
            target_state,
            retention_applied,
            tier_changed,
        }
    }
}

/// Parse memory operation from external payload string.
pub fn parse_memory_operation(value: &str) -> Option<MemoryOperation> {
    match value.trim().to_ascii_uppercase().as_str() {
        "PROMOTE_TO_ACTIVE" => Some(MemoryOperation::PromoteToActive),
        "DEMOTE_TO_DORMANT" => Some(MemoryOperation::DemoteToDormant),
        "ARCHIVE_ITEM" => Some(MemoryOperation::ArchiveItem),
        "FINALIZE_ARCHIVE" => Some(MemoryOperation::FinalizeArchive),
        "RETENTION_TRIGGER" => Some(MemoryOperation::RetentionTrigger),
        "VECTOR_TIER_SHIFT" => Some(MemoryOperation::VectorTierShift),
        _ => None,
    }
}

/// Determine memory transition permission and target state.
pub fn determine_memory_transition(
    current_lifecycle_state: &str,
    energy_mode: EnergyMode,
    storage_permission_flag: bool,
    operation_type: MemoryOperation,
    metadata_flags: MemoryMetadataFlags,
) -> MemoryDecision {
    if !storage_permission_flag {
        return MemoryDecision::deny("STORAGE_PERMISSION_REQUIRED", None, false, false);
    }

    if matches!(energy_mode, EnergyMode::Silent) && !metadata_flags.critical_reminder {
        return MemoryDecision::deny("SILENT_MODE_MEMORY_RESTRICTED", None, false, false);
    }

    let is_archived = current_lifecycle_state.trim().eq_ignore_ascii_case("ARCHIVED");
    if is_archived
        && matches!(operation_type, MemoryOperation::PromoteToActive)
        && !metadata_flags.allow_archived_reactivation
    {
        return MemoryDecision::deny("ARCHIVED_REACTIVATION_DENIED", None, true, false);
    }

    match operation_type {
        MemoryOperation::PromoteToActive => {
            MemoryDecision::allow(Some("ACTIVE".to_string()), false, true)
        }
        MemoryOperation::DemoteToDormant => {
            MemoryDecision::allow(Some("COMPLETED".to_string()), false, true)
        }
        MemoryOperation::ArchiveItem => {
            if is_archived {
                MemoryDecision::allow(Some("ARCHIVED".to_string()), true, false)
            } else {
                MemoryDecision::allow(Some("ARCHIVED".to_string()), true, true)
            }
        }
        MemoryOperation::FinalizeArchive => {
            if !is_archived {
                MemoryDecision::deny(
                    "FINALIZE_REQUIRES_ARCHIVED_STATE",
                    Some("ARCHIVED".to_string()),
                    true,
                    false,
                )
            } else {
                MemoryDecision::allow(Some("ARCHIVED".to_string()), true, false)
            }
        }
        MemoryOperation::RetentionTrigger => {
            if metadata_flags.retention_due {
                MemoryDecision::allow(Some("ARCHIVED".to_string()), true, true)
            } else {
                MemoryDecision::deny(
                    "RETENTION_WINDOW_NOT_REACHED",
                    Some("ARCHIVED".to_string()),
                    false,
                    false,
                )
            }
        }
        MemoryOperation::VectorTierShift => {
            MemoryDecision::allow(Some("DORMANT".to_string()), false, true)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{determine_memory_transition, parse_memory_operation, MemoryMetadataFlags, MemoryOperation};
    use apcos_os::energy_manager::EnergyMode;

    #[test]
    fn denies_when_storage_permission_missing() {
        let decision = determine_memory_transition(
            "ACTIVE",
            EnergyMode::Strategic,
            false,
            MemoryOperation::ArchiveItem,
            MemoryMetadataFlags::default(),
        );
        assert!(!decision.allowed);
        assert_eq!(decision.reason, "STORAGE_PERMISSION_REQUIRED");
    }

    #[test]
    fn parse_operation_handles_invalid_value() {
        assert_eq!(
            parse_memory_operation("PROMOTE_TO_ACTIVE"),
            Some(MemoryOperation::PromoteToActive)
        );
        assert!(parse_memory_operation("UNKNOWN").is_none());
    }
}
