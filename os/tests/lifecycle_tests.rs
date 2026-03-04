use apcos_os::runtime::lifecycle::{LifecycleError, LifecycleValidator, TaskState};

#[test]
fn lifecycle_rejects_invalid_transition() {
    let result = LifecycleValidator::validate_transition(TaskState::Archived, TaskState::Completed);
    assert!(matches!(
        result,
        Err(LifecycleError::InvalidTransition {
            from: TaskState::Archived,
            to: TaskState::Completed
        })
    ));
}

#[test]
fn lifecycle_accepts_valid_transition() {
    let result = LifecycleValidator::apply_transition(TaskState::Pending, TaskState::Completed);
    assert_eq!(result, Ok(TaskState::Completed));
}

