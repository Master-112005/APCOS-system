#[path = "../src/ipc.rs"]
mod ipc;

use apcos_os::event_bus::{Event, EventBus};
use apcos_os::logging::StructuredLogger;
use serde_json::json;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::Duration;

#[test]
fn test_valid_event_deserialization() {
    let line = r#"{"message_type":"EVENT","timestamp":1,"correlation_id":"cid-1","payload":{"event":"BatteryLow","percent":15}}"#;
    let parsed = ipc::parse_envelope_line(line, 4096);
    assert!(parsed.is_ok());
    let envelope = parsed.ok().flatten();
    assert!(envelope.is_some());
    assert_eq!(envelope.map(|value| value.correlation_id), Some("cid-1".to_string()));
}

#[test]
fn test_invalid_json_does_not_panic() {
    let line = r#"{"message_type":"EVENT""#;
    let parsed = ipc::parse_envelope_line(line, 4096);
    assert!(parsed.is_err());
}

#[test]
fn test_unknown_message_type_ignored() {
    let line = r#"{"message_type":"COMMAND","timestamp":1,"correlation_id":"cid-2","payload":{"event":"BatteryLow"}}"#;
    let parsed = ipc::parse_envelope_line(line, 4096);
    assert!(parsed.is_err());
}

#[test]
fn test_correlation_id_propagation() {
    let correlation = ipc::generate_correlation_id("test");
    let envelope = ipc::build_event_envelope("LifecycleValidated", json!({"allowed": true}), &correlation);
    assert_eq!(envelope.correlation_id, correlation);
}

#[test]
fn test_event_forwarded_to_bus() {
    let bus = EventBus::new(64, 4, 128);
    let logger = StructuredLogger::new("ipc-test");
    let hits = Arc::new(AtomicUsize::new(0));
    let hits_clone = hits.clone();

    let subscription = bus.subscribe(Event::BatteryLow, move |_| {
        hits_clone.fetch_add(1, Ordering::SeqCst);
    });
    assert!(subscription.is_ok());

    let line = r#"{"message_type":"EVENT","timestamp":1,"correlation_id":"cid-3","payload":{"event":"BatteryLow","percent":15}}"#;
    let parsed = ipc::parse_envelope_line(line, 4096).ok().flatten();
    assert!(parsed.is_some());
    let mut tracker = ipc::CorrelationTracker::new(16);
    let result = ipc::dispatch_incoming(
        &bus,
        parsed.unwrap_or_else(|| ipc::build_event_envelope("BatteryLow", json!({}), "fallback")),
        &mut tracker,
        &logger,
    );
    assert!(result.is_ok());
    thread::sleep(Duration::from_millis(50));
    assert_eq!(hits.load(Ordering::SeqCst), 1);
}

#[test]
fn test_no_recursion_loop() {
    let bus = EventBus::new(64, 4, 128);
    let logger = StructuredLogger::new("ipc-test");
    let line = r#"{"message_type":"STATE_UPDATE","timestamp":1,"correlation_id":"cid-4","payload":{"component":"Governor","mode":"LOW_POWER"}}"#;
    let parsed = ipc::parse_envelope_line(line, 4096).ok().flatten();
    assert!(parsed.is_some());
    let mut tracker = ipc::CorrelationTracker::new(16);
    let result = ipc::dispatch_incoming(
        &bus,
        parsed.unwrap_or_else(|| {
            ipc::build_event_envelope("LifecycleValidated", json!({"allowed": true}), "fallback")
        }),
        &mut tracker,
        &logger,
    );
    assert!(matches!(result, Ok(ipc::DispatchResult::StateUpdateAccepted)));
    assert!(bus.traces().is_empty());
}

#[test]
fn test_no_panic_on_large_payload() {
    let huge_data = "x".repeat(70 * 1024);
    let line = format!(
        r#"{{"message_type":"EVENT","timestamp":1,"correlation_id":"cid-big","payload":{{"event":"BatteryLow","blob":"{}"}}}}"#,
        huge_data
    );
    let parsed = ipc::parse_envelope_line(&line, 64 * 1024);
    assert!(parsed.is_err());
}

#[test]
fn test_auth_request_generates_auth_result() {
    let bus = EventBus::new(64, 4, 128);
    let logger = StructuredLogger::new("ipc-test");
    let line = r#"{"message_type":"AUTH_REQUEST","timestamp":1,"correlation_id":"cid-auth-1","payload":{"user_id":"owner","tier":"Owner","action":"CREATE_TASK","authenticated":true}}"#;
    let parsed = ipc::parse_envelope_line(line, 4096).ok().flatten();
    assert!(parsed.is_some());

    let mut tracker = ipc::CorrelationTracker::new(16);
    let result = ipc::dispatch_incoming(
        &bus,
        parsed.unwrap_or_else(|| ipc::build_event_envelope("BatteryLow", json!({}), "fallback")),
        &mut tracker,
        &logger,
    );
    assert!(matches!(result, Ok(ipc::DispatchResult::AuthResultGenerated(_))));

    if let Ok(ipc::DispatchResult::AuthResultGenerated(envelope)) = result {
        assert_eq!(envelope.message_type, ipc::MessageType::AuthResult);
        assert_eq!(envelope.correlation_id, "cid-auth-1");
        assert_eq!(envelope.payload.get("allowed").and_then(|value| value.as_bool()), Some(true));
    }
}

#[test]
fn test_auth_request_invalid_tier_denied() {
    let bus = EventBus::new(64, 4, 128);
    let logger = StructuredLogger::new("ipc-test");
    let line = r#"{"message_type":"AUTH_REQUEST","timestamp":1,"correlation_id":"cid-auth-2","payload":{"user_id":"u1","tier":"Unknown","action":"CREATE_TASK","authenticated":true}}"#;
    let parsed = ipc::parse_envelope_line(line, 4096).ok().flatten();
    assert!(parsed.is_some());

    let mut tracker = ipc::CorrelationTracker::new(16);
    let result = ipc::dispatch_incoming(
        &bus,
        parsed.unwrap_or_else(|| ipc::build_event_envelope("BatteryLow", json!({}), "fallback")),
        &mut tracker,
        &logger,
    );
    assert!(matches!(result, Ok(ipc::DispatchResult::AuthResultGenerated(_))));

    if let Ok(ipc::DispatchResult::AuthResultGenerated(envelope)) = result {
        assert_eq!(envelope.payload.get("allowed").and_then(|value| value.as_bool()), Some(false));
    }
}

#[test]
fn test_transition_validate_generates_transition_result() {
    let bus = EventBus::new(64, 4, 128);
    let logger = StructuredLogger::new("ipc-test");
    let line = r#"{"message_type":"TRANSITION_VALIDATE","timestamp":1,"correlation_id":"cid-transition-1","payload":{"current_state":"Pending","requested_state":"Completed"}}"#;
    let parsed = ipc::parse_envelope_line(line, 4096).ok().flatten();
    assert!(parsed.is_some());

    let mut tracker = ipc::CorrelationTracker::new(16);
    let result = ipc::dispatch_incoming(
        &bus,
        parsed.unwrap_or_else(|| ipc::build_event_envelope("BatteryLow", json!({}), "fallback")),
        &mut tracker,
        &logger,
    );
    assert!(matches!(
        result,
        Ok(ipc::DispatchResult::TransitionResultGenerated(_))
    ));

    if let Ok(ipc::DispatchResult::TransitionResultGenerated(envelope)) = result {
        assert_eq!(envelope.message_type, ipc::MessageType::TransitionResult);
        assert_eq!(
            envelope.payload.get("allowed").and_then(|value| value.as_bool()),
            Some(true)
        );
    }
}

#[test]
fn test_transition_validate_unknown_state_denied() {
    let bus = EventBus::new(64, 4, 128);
    let logger = StructuredLogger::new("ipc-test");
    let line = r#"{"message_type":"TRANSITION_VALIDATE","timestamp":1,"correlation_id":"cid-transition-2","payload":{"current_state":"Pending","requested_state":"Unknown"}}"#;
    let parsed = ipc::parse_envelope_line(line, 4096).ok().flatten();
    assert!(parsed.is_some());

    let mut tracker = ipc::CorrelationTracker::new(16);
    let result = ipc::dispatch_incoming(
        &bus,
        parsed.unwrap_or_else(|| ipc::build_event_envelope("BatteryLow", json!({}), "fallback")),
        &mut tracker,
        &logger,
    );
    assert!(matches!(
        result,
        Ok(ipc::DispatchResult::TransitionResultGenerated(_))
    ));

    if let Ok(ipc::DispatchResult::TransitionResultGenerated(envelope)) = result {
        assert_eq!(
            envelope.payload.get("allowed").and_then(|value| value.as_bool()),
            Some(false)
        );
        assert_eq!(
            envelope.payload.get("reason").and_then(|value| value.as_str()),
            Some("UNKNOWN_STATE")
        );
    }
}

#[test]
fn test_energy_validate_generates_energy_result() {
    let bus = EventBus::new(64, 4, 128);
    let logger = StructuredLogger::new("ipc-test");
    let line = r#"{"message_type":"ENERGY_VALIDATE","timestamp":1,"correlation_id":"cid-energy-1","payload":{"battery_percent":75,"execution_type":"LLM"}}"#;
    let parsed = ipc::parse_envelope_line(line, 4096).ok().flatten();
    assert!(parsed.is_some());

    let mut tracker = ipc::CorrelationTracker::new(16);
    let result = ipc::dispatch_incoming(
        &bus,
        parsed.unwrap_or_else(|| ipc::build_event_envelope("BatteryLow", json!({}), "fallback")),
        &mut tracker,
        &logger,
    );
    assert!(matches!(
        result,
        Ok(ipc::DispatchResult::EnergyResultGenerated(_))
    ));

    if let Ok(ipc::DispatchResult::EnergyResultGenerated(envelope)) = result {
        assert_eq!(envelope.message_type, ipc::MessageType::EnergyResult);
        assert_eq!(
            envelope.payload.get("allowed").and_then(|value| value.as_bool()),
            Some(true)
        );
    }
}

#[test]
fn test_energy_validate_blocks_background_in_reduced_mode() {
    let bus = EventBus::new(64, 4, 128);
    let logger = StructuredLogger::new("ipc-test");
    let line = r#"{"message_type":"ENERGY_VALIDATE","timestamp":1,"correlation_id":"cid-energy-2","payload":{"battery_percent":30,"execution_type":"BACKGROUND_TASK"}}"#;
    let parsed = ipc::parse_envelope_line(line, 4096).ok().flatten();
    assert!(parsed.is_some());

    let mut tracker = ipc::CorrelationTracker::new(16);
    let result = ipc::dispatch_incoming(
        &bus,
        parsed.unwrap_or_else(|| ipc::build_event_envelope("BatteryLow", json!({}), "fallback")),
        &mut tracker,
        &logger,
    );
    assert!(matches!(
        result,
        Ok(ipc::DispatchResult::EnergyResultGenerated(_))
    ));

    if let Ok(ipc::DispatchResult::EnergyResultGenerated(envelope)) = result {
        assert_eq!(
            envelope.payload.get("allowed").and_then(|value| value.as_bool()),
            Some(false)
        );
        assert_eq!(
            envelope.payload.get("reason").and_then(|value| value.as_str()),
            Some("BACKGROUND_BLOCKED_REDUCED")
        );
    }
}

#[test]
fn test_storage_validate_generates_storage_result() {
    let bus = EventBus::new(64, 4, 128);
    let logger = StructuredLogger::new("ipc-test");
    let line = r#"{"message_type":"STORAGE_VALIDATE","timestamp":1,"correlation_id":"cid-storage-1","payload":{"operation":"WRITE_TASK","lifecycle_state":"CREATED","energy_mode":"STRATEGIC","execution_type":"BACKGROUND_TASK","encryption_metadata_present":true,"encryption_key_id":"k1"}}"#;
    let parsed = ipc::parse_envelope_line(line, 4096).ok().flatten();
    assert!(parsed.is_some());

    let mut tracker = ipc::CorrelationTracker::new(16);
    let result = ipc::dispatch_incoming(
        &bus,
        parsed.unwrap_or_else(|| ipc::build_event_envelope("BatteryLow", json!({}), "fallback")),
        &mut tracker,
        &logger,
    );
    assert!(matches!(
        result,
        Ok(ipc::DispatchResult::StorageResultGenerated(_))
    ));
    if let Ok(ipc::DispatchResult::StorageResultGenerated(envelope)) = result {
        assert_eq!(envelope.message_type, ipc::MessageType::StorageResult);
        assert_eq!(
            envelope.payload.get("allowed").and_then(|value| value.as_bool()),
            Some(true)
        );
    }
    assert!(bus.traces().is_empty());
}

#[test]
fn test_storage_validate_denies_missing_encryption_metadata() {
    let bus = EventBus::new(64, 4, 128);
    let logger = StructuredLogger::new("ipc-test");
    let line = r#"{"message_type":"STORAGE_VALIDATE","timestamp":1,"correlation_id":"cid-storage-2","payload":{"operation":"WRITE_TASK","lifecycle_state":"CREATED","energy_mode":"STRATEGIC","execution_type":"BACKGROUND_TASK","encryption_metadata_present":false,"encryption_key_id":null}}"#;
    let parsed = ipc::parse_envelope_line(line, 4096).ok().flatten();
    assert!(parsed.is_some());

    let mut tracker = ipc::CorrelationTracker::new(16);
    let result = ipc::dispatch_incoming(
        &bus,
        parsed.unwrap_or_else(|| ipc::build_event_envelope("BatteryLow", json!({}), "fallback")),
        &mut tracker,
        &logger,
    );
    assert!(matches!(
        result,
        Ok(ipc::DispatchResult::StorageResultGenerated(_))
    ));
    if let Ok(ipc::DispatchResult::StorageResultGenerated(envelope)) = result {
        assert_eq!(
            envelope.payload.get("allowed").and_then(|value| value.as_bool()),
            Some(false)
        );
        assert_eq!(
            envelope.payload.get("reason").and_then(|value| value.as_str()),
            Some("ENCRYPTION_METADATA_MISSING")
        );
    }
}

#[test]
fn test_storage_validate_unknown_operation_denied() {
    let bus = EventBus::new(64, 4, 128);
    let logger = StructuredLogger::new("ipc-test");
    let line = r#"{"message_type":"STORAGE_VALIDATE","timestamp":1,"correlation_id":"cid-storage-3","payload":{"operation":"UNKNOWN","lifecycle_state":"CREATED","energy_mode":"STRATEGIC","execution_type":"BACKGROUND_TASK","encryption_metadata_present":true,"encryption_key_id":"k1"}}"#;
    let parsed = ipc::parse_envelope_line(line, 4096).ok().flatten();
    assert!(parsed.is_some());

    let mut tracker = ipc::CorrelationTracker::new(16);
    let result = ipc::dispatch_incoming(
        &bus,
        parsed.unwrap_or_else(|| ipc::build_event_envelope("BatteryLow", json!({}), "fallback")),
        &mut tracker,
        &logger,
    );
    assert!(matches!(
        result,
        Ok(ipc::DispatchResult::StorageResultGenerated(_))
    ));
    if let Ok(ipc::DispatchResult::StorageResultGenerated(envelope)) = result {
        assert_eq!(
            envelope.payload.get("allowed").and_then(|value| value.as_bool()),
            Some(false)
        );
        assert_eq!(
            envelope.payload.get("reason").and_then(|value| value.as_str()),
            Some("UNKNOWN_STORAGE_OPERATION")
        );
    }
}

#[test]
fn test_memory_validate_generates_memory_result() {
    let bus = EventBus::new(64, 4, 128);
    let logger = StructuredLogger::new("ipc-test");
    let line = r#"{"message_type":"MEMORY_VALIDATE","timestamp":1,"correlation_id":"cid-memory-1","payload":{"current_lifecycle_state":"ACTIVE","operation":"ARCHIVE_ITEM","energy_mode":"STRATEGIC","storage_permission_flag":true,"metadata_flags":{"retention_due":true}}}"#;
    let parsed = ipc::parse_envelope_line(line, 4096).ok().flatten();
    assert!(parsed.is_some());

    let mut tracker = ipc::CorrelationTracker::new(16);
    let result = ipc::dispatch_incoming(
        &bus,
        parsed.unwrap_or_else(|| ipc::build_event_envelope("BatteryLow", json!({}), "fallback")),
        &mut tracker,
        &logger,
    );
    assert!(matches!(
        result,
        Ok(ipc::DispatchResult::MemoryResultGenerated(_))
    ));
    if let Ok(ipc::DispatchResult::MemoryResultGenerated(envelope)) = result {
        assert_eq!(envelope.message_type, ipc::MessageType::MemoryResult);
        assert_eq!(
            envelope.payload.get("allowed").and_then(|value| value.as_bool()),
            Some(true)
        );
    }
    assert!(bus.traces().is_empty());
}

#[test]
fn test_memory_validate_denies_silent_mode() {
    let bus = EventBus::new(64, 4, 128);
    let logger = StructuredLogger::new("ipc-test");
    let line = r#"{"message_type":"MEMORY_VALIDATE","timestamp":1,"correlation_id":"cid-memory-2","payload":{"current_lifecycle_state":"ACTIVE","operation":"DEMOTE_TO_DORMANT","energy_mode":"SILENT","storage_permission_flag":true,"metadata_flags":{"critical_reminder":false}}}"#;
    let parsed = ipc::parse_envelope_line(line, 4096).ok().flatten();
    assert!(parsed.is_some());

    let mut tracker = ipc::CorrelationTracker::new(16);
    let result = ipc::dispatch_incoming(
        &bus,
        parsed.unwrap_or_else(|| ipc::build_event_envelope("BatteryLow", json!({}), "fallback")),
        &mut tracker,
        &logger,
    );
    assert!(matches!(
        result,
        Ok(ipc::DispatchResult::MemoryResultGenerated(_))
    ));
    if let Ok(ipc::DispatchResult::MemoryResultGenerated(envelope)) = result {
        assert_eq!(
            envelope.payload.get("allowed").and_then(|value| value.as_bool()),
            Some(false)
        );
        assert_eq!(
            envelope.payload.get("reason").and_then(|value| value.as_str()),
            Some("SILENT_MODE_MEMORY_RESTRICTED")
        );
    }
}

#[test]
fn test_memory_validate_unknown_operation_denied() {
    let bus = EventBus::new(64, 4, 128);
    let logger = StructuredLogger::new("ipc-test");
    let line = r#"{"message_type":"MEMORY_VALIDATE","timestamp":1,"correlation_id":"cid-memory-3","payload":{"current_lifecycle_state":"ACTIVE","operation":"UNKNOWN","energy_mode":"STRATEGIC","storage_permission_flag":true,"metadata_flags":{}}}"#;
    let parsed = ipc::parse_envelope_line(line, 4096).ok().flatten();
    assert!(parsed.is_some());

    let mut tracker = ipc::CorrelationTracker::new(16);
    let result = ipc::dispatch_incoming(
        &bus,
        parsed.unwrap_or_else(|| ipc::build_event_envelope("BatteryLow", json!({}), "fallback")),
        &mut tracker,
        &logger,
    );
    assert!(matches!(
        result,
        Ok(ipc::DispatchResult::MemoryResultGenerated(_))
    ));
    if let Ok(ipc::DispatchResult::MemoryResultGenerated(envelope)) = result {
        assert_eq!(
            envelope.payload.get("allowed").and_then(|value| value.as_bool()),
            Some(false)
        );
        assert_eq!(
            envelope.payload.get("reason").and_then(|value| value.as_str()),
            Some("UNKNOWN_MEMORY_OPERATION")
        );
    }
}
