//! APCOS OS supervisor binary entrypoint.

mod ipc;

use apcos_os::energy_manager::{EnergyConfig, EnergyManager, EnergySample};
use apcos_os::event_bus::{Event, EventBus};
use apcos_os::logging::StructuredLogger;
use apcos_os::runtime::lifecycle::{LifecycleValidator, TaskState};
use apcos_os::runtime::service_registry::{Service, ServiceRegistry};
use apcos_os::secure_storage::SecureStorage;
use serde_json::json;
use std::error::Error;

struct SupervisorService {
    name: String,
    running: bool,
}

impl SupervisorService {
    fn new(name: &str) -> Self {
        Self {
            name: name.to_string(),
            running: false,
        }
    }
}

impl Service for SupervisorService {
    fn name(&self) -> &str {
        &self.name
    }

    fn start(&mut self) -> Result<(), String> {
        self.running = true;
        Ok(())
    }

    fn stop(&mut self) -> Result<(), String> {
        self.running = false;
        Ok(())
    }

    fn is_running(&self) -> bool {
        self.running
    }
}

fn run() -> Result<(), Box<dyn Error>> {
    let logger = StructuredLogger::new("os-main");
    logger.info("APCOS OS supervisor starting")?;

    let bus = EventBus::new(128, 8, 256);
    let logger_clone = logger.clone();
    let _subscription = bus.subscribe(Event::BatteryLow, move |_| {
        let _ = logger_clone.warn("Battery low event received");
    })?;

    let lifecycle_check = LifecycleValidator::validate_transition(TaskState::Pending, TaskState::Completed);
    if lifecycle_check.is_err() {
        logger.error("Lifecycle validation failed for startup probe")?;
    } else {
        bus.publish(Event::LifecycleValidated, "os-main")?;
    }

    let mut energy_manager = EnergyManager::new(EnergyConfig::default());
    let _policy = energy_manager.evaluate_and_publish(
        EnergySample {
            cpu_percent: 10.0,
            battery_percent: 95.0,
            thermal_celsius: 35.0,
            on_external_power: true,
        },
        &bus,
        "energy-manager",
    )?;

    let storage = SecureStorage::with_generated_key();
    let encrypted = storage.encrypt(b"bootstrap-probe", b"os-main")?;
    let _decrypted = storage.decrypt(&encrypted, b"os-main")?;

    let mut registry = ServiceRegistry::default();
    registry.register_service(Box::new(SupervisorService::new("voice-service")), vec![])?;
    registry.start_all()?;
    registry.stop_all()?;

    // Optional Stage 11 bridge startup:
    // apcos_os --ipc-python services/ipc/rust_bridge.py
    let args: Vec<String> = std::env::args().collect();
    if args.len() >= 3 && args.get(1).map(|value| value.as_str()) == Some("--ipc-python") {
        if let Some(script_path) = args.get(2) {
            let mut bridge = ipc::PythonBridgeProcess::spawn("python", script_path, logger.clone())?;
            let correlation_id = ipc::generate_correlation_id("rust-event");
            let envelope = ipc::build_event_envelope(
                "LifecycleValidated",
                json!({"allowed": true}),
                &correlation_id,
            );
            bridge.send_envelope(&envelope)?;
            let _ = logger.info("IPC bridge initialized and bootstrap event sent.");
        }
    }

    bus.shutdown()?;
    logger.info("APCOS OS supervisor initialized")?;
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("apcos_os startup error: {error}");
    }
}
