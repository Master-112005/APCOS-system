use apcos_os::identity::access_control::{
    authorize, authorize_with_tier_string, IdentityContext,
};
use apcos_os::identity::tier_policy::Tier;

#[test]
fn test_owner_allowed_create() {
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
fn test_guest_denied_create() {
    let result = authorize(
        IdentityContext {
            user_id: "guest".to_string(),
            tier: Tier::Guest,
            authenticated: true,
        },
        "CREATE_TASK".to_string(),
    );
    assert!(!result.allowed);
}

#[test]
fn test_family_denied_cancel() {
    let result = authorize(
        IdentityContext {
            user_id: "family".to_string(),
            tier: Tier::Family,
            authenticated: true,
        },
        "CANCEL_TASK".to_string(),
    );
    assert!(!result.allowed);
}

#[test]
fn test_unauthenticated_denied() {
    let result = authorize(
        IdentityContext {
            user_id: "owner".to_string(),
            tier: Tier::Owner,
            authenticated: false,
        },
        "COMPLETE_TASK".to_string(),
    );
    assert!(!result.allowed);
}

#[test]
fn test_invalid_tier_handled() {
    let result = authorize_with_tier_string(
        "user".to_string(),
        "InvalidTier",
        true,
        "CREATE_TASK".to_string(),
    );
    assert!(!result.allowed);
    assert_eq!(result.reason.as_deref(), Some("INVALID_TIER"));
}

#[test]
fn test_no_panic_on_unknown_action() {
    let result = authorize(
        IdentityContext {
            user_id: "owner".to_string(),
            tier: Tier::Owner,
            authenticated: true,
        },
        "UNKNOWN_ACTION".to_string(),
    );
    assert!(!result.allowed);
}

