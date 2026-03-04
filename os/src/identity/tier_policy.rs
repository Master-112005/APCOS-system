//! System identity tier policy definitions.

/// Supported identity tiers at OS supervision boundary.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Tier {
    Owner,
    Family,
    Guest,
}

/// Parse tier string from IPC payload.
pub fn parse_tier(value: &str) -> Option<Tier> {
    match value.trim().to_ascii_lowercase().as_str() {
        "owner" => Some(Tier::Owner),
        "family" => Some(Tier::Family),
        "guest" => Some(Tier::Guest),
        _ => None,
    }
}

fn normalize_action(value: &str) -> String {
    value.trim().to_ascii_uppercase()
}

/// Check whether a tier is allowed to execute an action identifier.
///
/// Supported actions:
/// - CREATE_TASK
/// - COMPLETE_TASK
/// - CANCEL_TASK
/// - STRATEGY
pub fn is_allowed(tier: &Tier, action: &str) -> bool {
    let action_name = normalize_action(action);
    match tier {
        Tier::Owner => matches!(
            action_name.as_str(),
            "CREATE_TASK" | "COMPLETE_TASK" | "CANCEL_TASK" | "STRATEGY"
        ),
        Tier::Family => matches!(
            action_name.as_str(),
            "CREATE_TASK" | "COMPLETE_TASK" | "STRATEGY"
        ),
        Tier::Guest => false,
    }
}

#[cfg(test)]
mod tests {
    use super::{is_allowed, parse_tier, Tier};

    #[test]
    fn parses_tier_values() {
        assert_eq!(parse_tier("Owner"), Some(Tier::Owner));
        assert_eq!(parse_tier("family"), Some(Tier::Family));
        assert_eq!(parse_tier("guest"), Some(Tier::Guest));
        assert_eq!(parse_tier("unknown"), None);
    }

    #[test]
    fn policy_matrix_is_enforced() {
        assert!(is_allowed(&Tier::Owner, "CREATE_TASK"));
        assert!(is_allowed(&Tier::Family, "CREATE_TASK"));
        assert!(!is_allowed(&Tier::Family, "CANCEL_TASK"));
        assert!(!is_allowed(&Tier::Guest, "STRATEGY"));
    }
}
