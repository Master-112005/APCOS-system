//! Voice authentication stubs for future OS-level identity enforcement.

use crate::identity::access_control::IdentityContext;
use crate::identity::tier_policy::Tier;

/// Authenticated identity context returned by voice authenticator.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct VoiceIdentity {
    pub user_id: String,
    pub tier: Tier,
    pub authenticated: bool,
}

/// Deterministic stage-10 voice authentication stub.
#[derive(Default)]
pub struct VoiceAuthenticator;

impl VoiceAuthenticator {
    /// Authenticate from a marker string.
    ///
    /// This is intentionally a stub and does not perform biometric matching.
    pub fn authenticate_stub(&self, marker: &str) -> VoiceIdentity {
        let normalized = marker.trim().to_lowercase();
        if normalized.contains("guest") {
            VoiceIdentity {
                user_id: "guest".to_string(),
                tier: Tier::Guest,
                authenticated: true,
            }
        } else if normalized.contains("family") {
            VoiceIdentity {
                user_id: "family".to_string(),
                tier: Tier::Family,
                authenticated: true,
            }
        } else {
            VoiceIdentity {
                user_id: "owner".to_string(),
                tier: Tier::Owner,
                authenticated: true,
            }
        }
    }

    /// Validate and convert incoming request identity context.
    ///
    /// This stub intentionally performs only shape/authentication checks.
    pub fn validate_request_identity(&self, identity: IdentityContext) -> Result<IdentityContext, String> {
        if !identity.authenticated {
            return Err("UNAUTHENTICATED".to_string());
        }
        if identity.user_id.trim().is_empty() {
            return Err("INVALID_USER".to_string());
        }
        Ok(identity)
    }
}
