//! Deterministic access control checks for OS-level gatekeeping.

use crate::identity::tier_policy::{is_allowed, parse_tier, Tier};

/// Immutable identity context for one authorization request.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct IdentityContext {
    pub user_id: String,
    pub tier: Tier,
    pub authenticated: bool,
}

/// Structured authorization decision.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct AuthResult {
    pub allowed: bool,
    pub reason: Option<String>,
}

/// Access control evaluator.
#[derive(Default)]
pub struct AccessControl;

impl AccessControl {
    /// Authorize action for identity context.
    pub fn authorize(&self, identity: IdentityContext, action: String) -> AuthResult {
        if !identity.authenticated {
            return AuthResult {
                allowed: false,
                reason: Some("UNAUTHENTICATED".to_string()),
            };
        }
        if identity.user_id.trim().is_empty() {
            return AuthResult {
                allowed: false,
                reason: Some("INVALID_USER".to_string()),
            };
        }
        if action.trim().is_empty() {
            return AuthResult {
                allowed: false,
                reason: Some("INVALID_ACTION".to_string()),
            };
        }

        if is_allowed(&identity.tier, &action) {
            AuthResult {
                allowed: true,
                reason: None,
            }
        } else {
            AuthResult {
                allowed: false,
                reason: Some("ACCESS_DENIED".to_string()),
            }
        }
    }
}

/// Stateless authorization convenience API.
pub fn authorize(identity: IdentityContext, action: String) -> AuthResult {
    AccessControl.authorize(identity, action)
}

/// Authorize using tier string from IPC request.
pub fn authorize_with_tier_string(
    user_id: String,
    tier_value: &str,
    authenticated: bool,
    action: String,
) -> AuthResult {
    match parse_tier(tier_value) {
        Some(tier) => authorize(
            IdentityContext {
                user_id,
                tier,
                authenticated,
            },
            action,
        ),
        None => AuthResult {
            allowed: false,
            reason: Some("INVALID_TIER".to_string()),
        },
    }
}

#[cfg(test)]
mod tests {
    use super::{authorize, authorize_with_tier_string, IdentityContext};
    use crate::identity::tier_policy::Tier;

    #[test]
    fn owner_allowed_create() {
        let result = authorize(
            IdentityContext {
                user_id: "owner".to_string(),
                tier: Tier::Owner,
                authenticated: true,
            },
            "CREATE_TASK".to_string(),
        );
        assert!(result.allowed);
    }

    #[test]
    fn unauthenticated_denied() {
        let result = authorize(
            IdentityContext {
                user_id: "owner".to_string(),
                tier: Tier::Owner,
                authenticated: false,
            },
            "CREATE_TASK".to_string(),
        );
        assert!(!result.allowed);
    }

    #[test]
    fn invalid_tier_handled() {
        let result = authorize_with_tier_string(
            "user".to_string(),
            "unknown",
            true,
            "CREATE_TASK".to_string(),
        );
        assert!(!result.allowed);
        assert_eq!(result.reason.as_deref(), Some("INVALID_TIER"));
    }
}
