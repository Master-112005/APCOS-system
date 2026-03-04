//! Supervisory task lifecycle validation boundary.

use thiserror::Error;

/// System-level canonical lifecycle states.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TaskState {
    Pending,
    Completed,
    Archived,
}

/// Structured lifecycle validation result returned over IPC.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LifecycleResult {
    pub allowed: bool,
    pub reason: Option<String>,
}

#[derive(Debug, Error, PartialEq, Eq)]
pub enum LifecycleError {
    #[error("invalid lifecycle transition from {from:?} to {to:?}")]
    InvalidTransition { from: TaskState, to: TaskState },
}

/// Parse task state from external payload safely.
pub fn parse_task_state(value: &str) -> Option<TaskState> {
    match value.trim().to_ascii_lowercase().as_str() {
        "pending" => Some(TaskState::Pending),
        "completed" => Some(TaskState::Completed),
        "archived" => Some(TaskState::Archived),
        _ => None,
    }
}

/// Deterministic transition matrix.
pub fn is_valid_transition(from: TaskState, to: TaskState) -> bool {
    matches!(
        (from, to),
        (TaskState::Pending, TaskState::Completed)
            | (TaskState::Pending, TaskState::Archived)
            | (TaskState::Completed, TaskState::Archived)
    )
}

/// Validate a transition and return structured decision.
pub fn validate_transition(current_state: TaskState, requested_state: TaskState) -> LifecycleResult {
    if current_state == TaskState::Archived {
        return LifecycleResult {
            allowed: false,
            reason: Some("ARCHIVED_TERMINAL".to_string()),
        };
    }
    if is_valid_transition(current_state, requested_state) {
        LifecycleResult {
            allowed: true,
            reason: None,
        }
    } else {
        LifecycleResult {
            allowed: false,
            reason: Some("INVALID_TRANSITION".to_string()),
        }
    }
}

/// Validate a transition from raw state strings.
pub fn validate_transition_from_str(
    current_state: &str,
    requested_state: &str,
) -> LifecycleResult {
    let current = parse_task_state(current_state);
    let requested = parse_task_state(requested_state);
    match (current, requested) {
        (Some(src), Some(dst)) => validate_transition(src, dst),
        _ => LifecycleResult {
            allowed: false,
            reason: Some("UNKNOWN_STATE".to_string()),
        },
    }
}

/// Deterministic lifecycle transition validator.
#[derive(Default)]
pub struct LifecycleValidator;

impl LifecycleValidator {
    /// Validate a proposed state transition.
    pub fn validate_transition(from: TaskState, to: TaskState) -> Result<(), LifecycleError> {
        let result = validate_transition(from, to);
        if result.allowed {
            Ok(())
        } else {
            Err(LifecycleError::InvalidTransition { from, to })
        }
    }

    /// Apply a state transition if valid.
    pub fn apply_transition(from: TaskState, to: TaskState) -> Result<TaskState, LifecycleError> {
        Self::validate_transition(from, to)?;
        Ok(to)
    }
}

#[cfg(test)]
mod tests {
    use super::{
        is_valid_transition, parse_task_state, validate_transition, validate_transition_from_str,
        LifecycleValidator, TaskState,
    };

    #[test]
    fn accepts_expected_transitions() {
        let ok_one = LifecycleValidator::validate_transition(TaskState::Pending, TaskState::Completed);
        let ok_two = LifecycleValidator::validate_transition(TaskState::Pending, TaskState::Archived);
        let ok_three =
            LifecycleValidator::validate_transition(TaskState::Completed, TaskState::Archived);
        assert!(ok_one.is_ok());
        assert!(ok_two.is_ok());
        assert!(ok_three.is_ok());
    }

    #[test]
    fn rejects_invalid_transition() {
        let invalid =
            LifecycleValidator::validate_transition(TaskState::Archived, TaskState::Completed);
        assert!(invalid.is_err());
    }

    #[test]
    fn parses_state_values() {
        assert_eq!(parse_task_state("Pending"), Some(TaskState::Pending));
        assert_eq!(parse_task_state("completed"), Some(TaskState::Completed));
        assert_eq!(parse_task_state("Archived"), Some(TaskState::Archived));
        assert_eq!(parse_task_state("other"), None);
    }

    #[test]
    fn validates_transition_result_struct() {
        let allowed = validate_transition(TaskState::Pending, TaskState::Completed);
        assert!(allowed.allowed);
        let denied = validate_transition(TaskState::Archived, TaskState::Completed);
        assert!(!denied.allowed);
        assert_eq!(denied.reason.as_deref(), Some("ARCHIVED_TERMINAL"));
    }

    #[test]
    fn handles_unknown_states() {
        let result = validate_transition_from_str("Pending", "UNKNOWN");
        assert!(!result.allowed);
        assert_eq!(result.reason.as_deref(), Some("UNKNOWN_STATE"));
    }

    #[test]
    fn exposes_transition_matrix() {
        assert!(is_valid_transition(TaskState::Pending, TaskState::Completed));
        assert!(!is_valid_transition(TaskState::Completed, TaskState::Pending));
    }
}
