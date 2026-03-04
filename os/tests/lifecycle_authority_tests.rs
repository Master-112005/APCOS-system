use apcos_os::runtime::lifecycle::{
    is_valid_transition, validate_transition, validate_transition_from_str, TaskState,
};

#[test]
fn valid_pending_to_completed() {
    let result = validate_transition(TaskState::Pending, TaskState::Completed);
    assert!(result.allowed);
}

#[test]
fn valid_pending_to_archived() {
    let result = validate_transition(TaskState::Pending, TaskState::Archived);
    assert!(result.allowed);
}

#[test]
fn valid_completed_to_archived() {
    let result = validate_transition(TaskState::Completed, TaskState::Archived);
    assert!(result.allowed);
}

#[test]
fn invalid_completed_to_pending() {
    let result = validate_transition(TaskState::Completed, TaskState::Pending);
    assert!(!result.allowed);
}

#[test]
fn invalid_archived_to_pending() {
    let result = validate_transition(TaskState::Archived, TaskState::Pending);
    assert!(!result.allowed);
    assert_eq!(result.reason.as_deref(), Some("ARCHIVED_TERMINAL"));
}

#[test]
fn invalid_archived_to_completed() {
    let result = validate_transition(TaskState::Archived, TaskState::Completed);
    assert!(!result.allowed);
    assert_eq!(result.reason.as_deref(), Some("ARCHIVED_TERMINAL"));
}

#[test]
fn idempotent_pending_to_pending_denied() {
    let result = validate_transition(TaskState::Pending, TaskState::Pending);
    assert!(!result.allowed);
}

#[test]
fn no_panic_on_unknown_state() {
    let result = validate_transition_from_str("Pending", "Unknown");
    assert!(!result.allowed);
    assert_eq!(result.reason.as_deref(), Some("UNKNOWN_STATE"));
}

#[test]
fn transition_matrix_consistency() {
    assert!(is_valid_transition(TaskState::Pending, TaskState::Completed));
    assert!(!is_valid_transition(TaskState::Archived, TaskState::Pending));
}

