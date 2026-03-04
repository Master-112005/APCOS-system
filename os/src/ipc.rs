//! Minimal JSON-over-stdio IPC bridge for Rust supervisor <-> Python runtime.
#![allow(dead_code)]

#[path = "runtime/memory_authority.rs"]
mod memory_authority;

use apcos_os::event_bus::{Event, EventBus};
use apcos_os::energy_manager::{authorize_execution, determine_mode, parse_execution_type};
use apcos_os::identity::access_control::{authorize_with_tier_string, AuthResult};
use apcos_os::logging::StructuredLogger;
use apcos_os::runtime::lifecycle::validate_transition_from_str;
use apcos_os::secure_storage::{authorize_storage, parse_energy_mode, parse_storage_operation};
use memory_authority::{
    determine_memory_transition, parse_memory_operation, MemoryDecision, MemoryMetadataFlags,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::{HashSet, VecDeque};
use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::time::{SystemTime, UNIX_EPOCH};
use thiserror::Error;

const DEFAULT_MAX_MESSAGE_BYTES: usize = 64 * 1024;
const DEFAULT_MAX_TRACKED_CORRELATIONS: usize = 2048;
pub const IPC_SCHEMA_VERSION: u16 = 1;

/// Supported IPC envelope message classes.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum MessageType {
    Event,
    StateUpdate,
    AuthRequest,
    AuthResult,
    TransitionValidate,
    TransitionResult,
    EnergyValidate,
    EnergyResult,
    StorageValidate,
    StorageResult,
    MemoryValidate,
    MemoryResult,
}

/// Strict IPC envelope shared between Rust and Python layers.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct IpcEnvelope {
    pub message_type: MessageType,
    pub timestamp: u128,
    pub correlation_id: String,
    pub payload: Value,
}

#[derive(Debug, Error)]
pub enum IpcError {
    #[error("payload exceeds max message size")]
    MessageTooLarge,
    #[error("invalid JSON envelope")]
    InvalidJson,
    #[error("invalid envelope schema")]
    InvalidSchema,
    #[error("I/O error")]
    Io(#[from] std::io::Error),
}

/// Result of dispatching an incoming IPC envelope.
#[derive(Clone, Debug, PartialEq)]
pub enum DispatchResult {
    Ignored,
    DuplicateIgnored,
    EventForwarded(Event),
    StateUpdateAccepted,
    AuthResultGenerated(IpcEnvelope),
    TransitionResultGenerated(IpcEnvelope),
    EnergyResultGenerated(IpcEnvelope),
    StorageResultGenerated(IpcEnvelope),
    MemoryResultGenerated(IpcEnvelope),
}

/// Correlation-id tracker for dedupe and loop suppression.
#[derive(Default)]
pub struct CorrelationTracker {
    set: HashSet<String>,
    queue: VecDeque<String>,
    max_entries: usize,
}

impl CorrelationTracker {
    pub fn new(max_entries: usize) -> Self {
        Self {
            set: HashSet::new(),
            queue: VecDeque::new(),
            max_entries: max_entries.max(1),
        }
    }

    /// Mark correlation id as seen. Returns `true` when first observed.
    pub fn mark_seen(&mut self, correlation_id: &str) -> bool {
        if self.set.contains(correlation_id) {
            return false;
        }
        self.set.insert(correlation_id.to_string());
        self.queue.push_back(correlation_id.to_string());
        while self.queue.len() > self.max_entries {
            if let Some(oldest) = self.queue.pop_front() {
                self.set.remove(&oldest);
            }
        }
        true
    }
}

/// IPC process wrapper supervising a Python child bridge.
pub struct PythonBridgeProcess {
    child: Child,
    child_stdin: ChildStdin,
    child_stdout: BufReader<ChildStdout>,
    max_message_bytes: usize,
    tracker: CorrelationTracker,
    logger: StructuredLogger,
}

impl PythonBridgeProcess {
    /// Spawn the Python bridge process with piped stdin/stdout.
    pub fn spawn(
        python_executable: &str,
        script_path: &str,
        logger: StructuredLogger,
    ) -> Result<Self, IpcError> {
        let mut child = Command::new(python_executable)
            .arg(script_path)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()?;

        let child_stdin = child.stdin.take().ok_or(IpcError::InvalidSchema)?;
        let child_stdout = child.stdout.take().ok_or(IpcError::InvalidSchema)?;

        Ok(Self {
            child,
            child_stdin,
            child_stdout: BufReader::new(child_stdout),
            max_message_bytes: DEFAULT_MAX_MESSAGE_BYTES,
            tracker: CorrelationTracker::new(DEFAULT_MAX_TRACKED_CORRELATIONS),
            logger,
        })
    }

    /// Send a structured event envelope to Python.
    pub fn send_envelope(&mut self, envelope: &IpcEnvelope) -> Result<(), IpcError> {
        let encoded = serialize_envelope(envelope)?;
        self.child_stdin.write_all(encoded.as_bytes())?;
        self.child_stdin.write_all(b"\n")?;
        self.child_stdin.flush()?;
        let _ = self.tracker.mark_seen(&envelope.correlation_id);
        Ok(())
    }

    /// Read and dispatch one line from Python bridge. Blocking read.
    pub fn read_and_dispatch_once(&mut self, event_bus: &EventBus) -> Result<DispatchResult, IpcError> {
        let mut line = String::new();
        let bytes = self.child_stdout.read_line(&mut line)?;
        if bytes == 0 {
            return Ok(DispatchResult::Ignored);
        }
        let envelope = match parse_envelope_line(&line, self.max_message_bytes)? {
            Some(value) => value,
            None => return Ok(DispatchResult::Ignored),
        };
        let result = dispatch_incoming(event_bus, envelope, &mut self.tracker, &self.logger)?;
        match &result {
            DispatchResult::AuthResultGenerated(response)
            | DispatchResult::TransitionResultGenerated(response)
            | DispatchResult::EnergyResultGenerated(response)
            | DispatchResult::StorageResultGenerated(response)
            | DispatchResult::MemoryResultGenerated(response) => {
                self.send_envelope(response)?;
            }
            _ => {}
        }
        Ok(result)
    }

    /// Attempt clean shutdown of Python bridge child.
    pub fn shutdown(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

impl Drop for PythonBridgeProcess {
    fn drop(&mut self) {
        self.shutdown();
    }
}

/// Build a Rust-origin supervisor event envelope.
pub fn build_event_envelope(event_name: &str, payload: Value, correlation_id: &str) -> IpcEnvelope {
    IpcEnvelope {
        message_type: MessageType::Event,
        timestamp: now_timestamp_ms(),
        correlation_id: correlation_id.to_string(),
        payload: json!({
            "event": event_name,
            "data": payload
        }),
    }
}

/// Build an AUTH_RESULT envelope for a matching correlation id.
pub fn build_auth_result_envelope(correlation_id: &str, result: &AuthResult) -> IpcEnvelope {
    IpcEnvelope {
        message_type: MessageType::AuthResult,
        timestamp: now_timestamp_ms(),
        correlation_id: correlation_id.to_string(),
        payload: json!({
            "allowed": result.allowed,
            "reason": result.reason
        }),
    }
}

/// Build a TRANSITION_RESULT envelope for a matching correlation id.
pub fn build_transition_result_envelope(
    correlation_id: &str,
    allowed: bool,
    reason: Option<String>,
) -> IpcEnvelope {
    IpcEnvelope {
        message_type: MessageType::TransitionResult,
        timestamp: now_timestamp_ms(),
        correlation_id: correlation_id.to_string(),
        payload: json!({
            "allowed": allowed,
            "reason": reason
        }),
    }
}

/// Build an ENERGY_RESULT envelope for a matching correlation id.
pub fn build_energy_result_envelope(
    correlation_id: &str,
    allowed: bool,
    reason: Option<String>,
) -> IpcEnvelope {
    IpcEnvelope {
        message_type: MessageType::EnergyResult,
        timestamp: now_timestamp_ms(),
        correlation_id: correlation_id.to_string(),
        payload: json!({
            "allowed": allowed,
            "reason": reason
        }),
    }
}

/// Build a STORAGE_RESULT envelope for a matching correlation id.
pub fn build_storage_result_envelope(
    correlation_id: &str,
    allowed: bool,
    reason: Option<String>,
    retention_applied: bool,
    encryption_verified: bool,
) -> IpcEnvelope {
    IpcEnvelope {
        message_type: MessageType::StorageResult,
        timestamp: now_timestamp_ms(),
        correlation_id: correlation_id.to_string(),
        payload: json!({
            "allowed": allowed,
            "reason": reason,
            "retention_applied": retention_applied,
            "encryption_verified": encryption_verified
        }),
    }
}

/// Build a MEMORY_RESULT envelope for a matching correlation id.
pub fn build_memory_result_envelope(
    correlation_id: &str,
    decision: &MemoryDecision,
) -> IpcEnvelope {
    let reason = if decision.reason.is_empty() {
        None
    } else {
        Some(decision.reason.clone())
    };
    IpcEnvelope {
        message_type: MessageType::MemoryResult,
        timestamp: now_timestamp_ms(),
        correlation_id: correlation_id.to_string(),
        payload: json!({
            "allowed": decision.allowed,
            "reason": reason,
            "target_state": decision.target_state,
            "retention_applied": decision.retention_applied,
            "tier_changed": decision.tier_changed
        }),
    }
}

/// Serialize envelope into a compact JSON line.
pub fn serialize_envelope(envelope: &IpcEnvelope) -> Result<String, IpcError> {
    serde_json::to_string(envelope).map_err(|_| IpcError::InvalidJson)
}

/// Parse and validate a single JSON line envelope.
pub fn parse_envelope_line(line: &str, max_bytes: usize) -> Result<Option<IpcEnvelope>, IpcError> {
    let trimmed = line.trim();
    if trimmed.is_empty() {
        return Ok(None);
    }
    if trimmed.len() > max_bytes.max(1) {
        return Err(IpcError::MessageTooLarge);
    }
    let envelope: IpcEnvelope = serde_json::from_str(trimmed).map_err(|_| IpcError::InvalidJson)?;
    validate_envelope(&envelope)?;
    Ok(Some(envelope))
}

/// Dispatch envelope with strict message-type behavior.
pub fn dispatch_incoming(
    event_bus: &EventBus,
    envelope: IpcEnvelope,
    tracker: &mut CorrelationTracker,
    logger: &StructuredLogger,
) -> Result<DispatchResult, IpcError> {
    if !tracker.mark_seen(&envelope.correlation_id) {
        let _ = logger.warn("Duplicate correlation id ignored in IPC bridge.");
        return Ok(DispatchResult::DuplicateIgnored);
    }

    match envelope.message_type {
        MessageType::StateUpdate => {
            // Stage 11 rule: state updates never produce further events.
            Ok(DispatchResult::StateUpdateAccepted)
        }
        MessageType::Event => {
            let maybe_event = extract_event(&envelope.payload);
            if let Some(event) = maybe_event {
                let _ = event_bus.publish(event.clone(), "ipc-bridge");
                Ok(DispatchResult::EventForwarded(event))
            } else {
                let _ = logger.warn("IPC EVENT missing or unknown payload.event; ignored.");
                Ok(DispatchResult::Ignored)
            }
        }
        MessageType::AuthRequest => {
            let request = match parse_auth_request(&envelope.payload) {
                Some(value) => value,
                None => {
                    let _ = logger.warn("IPC AUTH_REQUEST payload invalid; denied.");
                    let denied = AuthResult {
                        allowed: false,
                        reason: Some("INVALID_AUTH_REQUEST".to_string()),
                    };
                    return Ok(DispatchResult::AuthResultGenerated(build_auth_result_envelope(
                        &envelope.correlation_id,
                        &denied,
                    )));
                }
            };

            let result = authorize_with_tier_string(
                request.user_id,
                &request.tier,
                request.authenticated,
                request.action,
            );
            let response = build_auth_result_envelope(&envelope.correlation_id, &result);
            Ok(DispatchResult::AuthResultGenerated(response))
        }
        MessageType::AuthResult => Ok(DispatchResult::Ignored),
        MessageType::TransitionValidate => {
            let request = match parse_transition_request(&envelope.payload) {
                Some(value) => value,
                None => {
                    let _ = logger.warn("IPC TRANSITION_VALIDATE payload invalid; denied.");
                    let response = build_transition_result_envelope(
                        &envelope.correlation_id,
                        false,
                        Some("INVALID_TRANSITION_REQUEST".to_string()),
                    );
                    return Ok(DispatchResult::TransitionResultGenerated(response));
                }
            };

            let validation = validate_transition_from_str(
                request.current_state.as_str(),
                request.requested_state.as_str(),
            );
            let response = build_transition_result_envelope(
                &envelope.correlation_id,
                validation.allowed,
                validation.reason,
            );
            Ok(DispatchResult::TransitionResultGenerated(response))
        }
        MessageType::TransitionResult => Ok(DispatchResult::Ignored),
        MessageType::EnergyValidate => {
            let request = match parse_energy_validate_request(&envelope.payload) {
                Some(value) => value,
                None => {
                    let _ = logger.warn("IPC ENERGY_VALIDATE payload invalid; denied.");
                    let response = build_energy_result_envelope(
                        &envelope.correlation_id,
                        false,
                        Some("INVALID_ENERGY_REQUEST".to_string()),
                    );
                    return Ok(DispatchResult::EnergyResultGenerated(response));
                }
            };

            let execution = match parse_execution_type(request.execution_type.as_str()) {
                Some(value) => value,
                None => {
                    let response = build_energy_result_envelope(
                        &envelope.correlation_id,
                        false,
                        Some("UNKNOWN_EXECUTION_TYPE".to_string()),
                    );
                    return Ok(DispatchResult::EnergyResultGenerated(response));
                }
            };

            let mode = determine_mode(request.battery_percent);
            let decision = authorize_execution(&mode, execution);
            let response =
                build_energy_result_envelope(&envelope.correlation_id, decision.allowed, decision.reason);
            Ok(DispatchResult::EnergyResultGenerated(response))
        }
        MessageType::EnergyResult => Ok(DispatchResult::Ignored),
        MessageType::StorageValidate => {
            let request = match parse_storage_validate_request(&envelope.payload) {
                Some(value) => value,
                None => {
                    let _ = logger.warn("IPC STORAGE_VALIDATE payload invalid; denied.");
                    let response = build_storage_result_envelope(
                        &envelope.correlation_id,
                        false,
                        Some("INVALID_STORAGE_REQUEST".to_string()),
                        false,
                        false,
                    );
                    return Ok(DispatchResult::StorageResultGenerated(response));
                }
            };

            let operation = match parse_storage_operation(request.operation.as_str()) {
                Some(value) => value,
                None => {
                    let response = build_storage_result_envelope(
                        &envelope.correlation_id,
                        false,
                        Some("UNKNOWN_STORAGE_OPERATION".to_string()),
                        false,
                        false,
                    );
                    return Ok(DispatchResult::StorageResultGenerated(response));
                }
            };

            let energy_mode = match parse_energy_mode(request.energy_mode.as_str()) {
                Some(value) => value,
                None => {
                    let response = build_storage_result_envelope(
                        &envelope.correlation_id,
                        false,
                        Some("UNKNOWN_ENERGY_MODE".to_string()),
                        false,
                        false,
                    );
                    return Ok(DispatchResult::StorageResultGenerated(response));
                }
            };

            let execution_type = match parse_execution_type(request.execution_type.as_str()) {
                Some(value) => value,
                None => {
                    let response = build_storage_result_envelope(
                        &envelope.correlation_id,
                        false,
                        Some("UNKNOWN_EXECUTION_TYPE".to_string()),
                        false,
                        false,
                    );
                    return Ok(DispatchResult::StorageResultGenerated(response));
                }
            };

            let decision = authorize_storage(
                operation,
                request.lifecycle_state.as_str(),
                energy_mode,
                execution_type,
                request.encryption_metadata_present,
                request.encryption_key_id,
            );
            let reason = if decision.reason.is_empty() {
                None
            } else {
                Some(decision.reason.clone())
            };
            let response = build_storage_result_envelope(
                &envelope.correlation_id,
                decision.allowed,
                reason,
                decision.retention_applied,
                decision.encryption_verified,
            );
            Ok(DispatchResult::StorageResultGenerated(response))
        }
        MessageType::StorageResult => Ok(DispatchResult::Ignored),
        MessageType::MemoryValidate => {
            let request = match parse_memory_validate_request(&envelope.payload) {
                Some(value) => value,
                None => {
                    let _ = logger.warn("IPC MEMORY_VALIDATE payload invalid; denied.");
                    let denied = MemoryDecision {
                        allowed: false,
                        reason: "INVALID_MEMORY_REQUEST".to_string(),
                        target_state: None,
                        retention_applied: false,
                        tier_changed: false,
                    };
                    let response = build_memory_result_envelope(&envelope.correlation_id, &denied);
                    return Ok(DispatchResult::MemoryResultGenerated(response));
                }
            };

            let operation = match parse_memory_operation(request.operation.as_str()) {
                Some(value) => value,
                None => {
                    let denied = MemoryDecision {
                        allowed: false,
                        reason: "UNKNOWN_MEMORY_OPERATION".to_string(),
                        target_state: None,
                        retention_applied: false,
                        tier_changed: false,
                    };
                    let response = build_memory_result_envelope(&envelope.correlation_id, &denied);
                    return Ok(DispatchResult::MemoryResultGenerated(response));
                }
            };

            let energy_mode = match parse_energy_mode(request.energy_mode.as_str()) {
                Some(value) => value,
                None => {
                    let denied = MemoryDecision {
                        allowed: false,
                        reason: "UNKNOWN_ENERGY_MODE".to_string(),
                        target_state: None,
                        retention_applied: false,
                        tier_changed: false,
                    };
                    let response = build_memory_result_envelope(&envelope.correlation_id, &denied);
                    return Ok(DispatchResult::MemoryResultGenerated(response));
                }
            };

            let metadata_flags = MemoryMetadataFlags {
                critical_reminder: request.metadata_flags.critical_reminder,
                allow_archived_reactivation: request.metadata_flags.allow_archived_reactivation,
                retention_due: request.metadata_flags.retention_due,
            };
            let decision = determine_memory_transition(
                request.current_lifecycle_state.as_str(),
                energy_mode,
                request.storage_permission_flag,
                operation,
                metadata_flags,
            );
            let response = build_memory_result_envelope(&envelope.correlation_id, &decision);
            Ok(DispatchResult::MemoryResultGenerated(response))
        }
        MessageType::MemoryResult => Ok(DispatchResult::Ignored),
    }
}

fn validate_envelope(envelope: &IpcEnvelope) -> Result<(), IpcError> {
    if envelope.correlation_id.trim().is_empty() || envelope.correlation_id.len() > 128 {
        return Err(IpcError::InvalidSchema);
    }
    if !envelope.payload.is_object() {
        return Err(IpcError::InvalidSchema);
    }
    Ok(())
}

fn extract_event(payload: &Value) -> Option<Event> {
    let event_name = payload.get("event")?.as_str()?;
    map_event_name(event_name)
}

#[derive(Debug, Deserialize)]
struct AuthRequestPayload {
    user_id: String,
    tier: String,
    action: String,
    #[serde(default = "default_authenticated")]
    authenticated: bool,
}

fn default_authenticated() -> bool {
    false
}

fn parse_auth_request(payload: &Value) -> Option<AuthRequestPayload> {
    serde_json::from_value(payload.clone()).ok()
}

#[derive(Debug, Deserialize)]
struct TransitionRequestPayload {
    current_state: String,
    requested_state: String,
}

fn parse_transition_request(payload: &Value) -> Option<TransitionRequestPayload> {
    serde_json::from_value(payload.clone()).ok()
}

#[derive(Debug, Deserialize)]
struct EnergyValidatePayload {
    battery_percent: u8,
    execution_type: String,
}

fn parse_energy_validate_request(payload: &Value) -> Option<EnergyValidatePayload> {
    serde_json::from_value(payload.clone()).ok()
}

#[derive(Debug, Deserialize)]
struct StorageValidatePayload {
    operation: String,
    lifecycle_state: String,
    energy_mode: String,
    execution_type: String,
    #[serde(default)]
    encryption_metadata_present: bool,
    encryption_key_id: Option<String>,
}

fn parse_storage_validate_request(payload: &Value) -> Option<StorageValidatePayload> {
    serde_json::from_value(payload.clone()).ok()
}

#[derive(Debug, Default, Deserialize)]
struct MemoryMetadataPayload {
    #[serde(default)]
    critical_reminder: bool,
    #[serde(default)]
    allow_archived_reactivation: bool,
    #[serde(default)]
    retention_due: bool,
}

#[derive(Debug, Deserialize)]
struct MemoryValidatePayload {
    current_lifecycle_state: String,
    operation: String,
    energy_mode: String,
    #[serde(default)]
    storage_permission_flag: bool,
    #[serde(default)]
    metadata_flags: MemoryMetadataPayload,
}

fn parse_memory_validate_request(payload: &Value) -> Option<MemoryValidatePayload> {
    serde_json::from_value(payload.clone()).ok()
}

fn map_event_name(value: &str) -> Option<Event> {
    match value {
        "IntentParsed" => Some(Event::IntentParsed),
        "LifecycleValidated" => Some(Event::LifecycleValidated),
        "TaskCreated" => Some(Event::TaskCreated),
        "TaskCompleted" => Some(Event::TaskCompleted),
        "TaskArchived" => Some(Event::TaskArchived),
        "BatteryLow" => Some(Event::BatteryLow),
        "ThermalHigh" => Some(Event::ThermalHigh),
        "SleepEntered" => Some(Event::SleepEntered),
        "SleepExited" => Some(Event::SleepExited),
        "IdentityChanged" => Some(Event::IdentityChanged),
        "ModelDowngrade" => Some(Event::ModelDowngrade),
        "ModelUnload" => Some(Event::ModelUnload),
        _ => None,
    }
}

/// Generate correlation id without shared mutable global state.
pub fn generate_correlation_id(prefix: &str) -> String {
    let base = now_timestamp_ms();
    format!("{prefix}-{base}")
}

fn now_timestamp_ms() -> u128 {
    match SystemTime::now().duration_since(UNIX_EPOCH) {
        Ok(duration) => duration.as_millis(),
        Err(_) => 0,
    }
}
