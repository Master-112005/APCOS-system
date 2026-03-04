#[path = "../src/runtime/memory_authority.rs"]
mod memory_authority;

use apcos_os::energy_manager::EnergyMode;
use memory_authority::{
    determine_memory_transition, parse_memory_operation, MemoryMetadataFlags, MemoryOperation,
};

#[test]
fn allowed_transition_with_storage_permission() {
    let decision = determine_memory_transition(
        "ACTIVE",
        EnergyMode::Strategic,
        true,
        MemoryOperation::ArchiveItem,
        MemoryMetadataFlags {
            retention_due: true,
            ..MemoryMetadataFlags::default()
        },
    );
    assert!(decision.allowed);
    assert_eq!(decision.target_state.as_deref(), Some("ARCHIVED"));
}

#[test]
fn denied_transition_without_storage_permission() {
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
fn retention_enforcement_denies_early_trigger() {
    let decision = determine_memory_transition(
        "COMPLETED",
        EnergyMode::Strategic,
        true,
        MemoryOperation::RetentionTrigger,
        MemoryMetadataFlags {
            retention_due: false,
            ..MemoryMetadataFlags::default()
        },
    );
    assert!(!decision.allowed);
    assert_eq!(decision.reason, "RETENTION_WINDOW_NOT_REACHED");
}

#[test]
fn energy_silent_mode_denial_for_non_critical_transition() {
    let decision = determine_memory_transition(
        "ACTIVE",
        EnergyMode::Silent,
        true,
        MemoryOperation::DemoteToDormant,
        MemoryMetadataFlags {
            critical_reminder: false,
            ..MemoryMetadataFlags::default()
        },
    );
    assert!(!decision.allowed);
    assert_eq!(decision.reason, "SILENT_MODE_MEMORY_RESTRICTED");
}

#[test]
fn invalid_operation_parsing() {
    assert!(parse_memory_operation("INVALID").is_none());
}

#[test]
fn no_forbidden_runtime_calls_in_memory_authority() {
    let source = include_str!("../src/runtime/memory_authority.rs");
    assert!(!source.contains("unwrap("));
    assert!(!source.contains("expect("));
    assert!(!source.contains("panic!"));
    assert!(!source.contains("unsafe"));
    assert!(!source.contains("std::fs"));
}
