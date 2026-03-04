//! APCOS Rust OS supervisor layer.
//!
//! This crate provides deterministic supervisory services:
//! - typed event bus orchestration
//! - lifecycle transition validation
//! - energy signal supervision
//! - secure storage primitives
//! - service lifecycle registry

pub mod energy_manager;
pub mod event_bus;
pub mod logging;
pub mod scheduler;
pub mod secure_storage;

pub mod runtime {
    pub mod lifecycle;
    pub mod service_registry;
}

pub mod identity {
    pub mod access_control;
    pub mod tier_policy;
    pub mod voice_auth;
}

