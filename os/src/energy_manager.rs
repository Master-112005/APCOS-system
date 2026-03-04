//! OS-level energy supervision and event signaling.

use crate::event_bus::{Event, EventBus, EventBusError};
use serde::{Deserialize, Serialize};
use thiserror::Error;

/// Energy thresholds used by the supervisor.
#[derive(Clone, Copy, Debug)]
pub struct EnergyConfig {
    pub cpu_high_percent: f32,
    pub battery_low_percent: f32,
    pub battery_critical_percent: f32,
    pub thermal_high_celsius: f32,
    pub thermal_critical_celsius: f32,
    pub thermal_recovery_cycles: u8,
}

impl Default for EnergyConfig {
    fn default() -> Self {
        Self {
            cpu_high_percent: 75.0,
            battery_low_percent: 20.0,
            battery_critical_percent: 10.0,
            thermal_high_celsius: 75.0,
            thermal_critical_celsius: 85.0,
            thermal_recovery_cycles: 3,
        }
    }
}

/// Closed-set supervisor energy modes.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub enum EnergyMode {
    Strategic,
    Reduced,
    Silent,
}

/// Compute execution classes that require energy authorization.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub enum ExecutionType {
    LLM,
    Proactive,
    BackgroundTask,
    CriticalReminder,
    Voice,
}

/// Structured energy authorization decision.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct EnergyDecision {
    pub allowed: bool,
    pub reason: Option<String>,
}

/// Determine current energy mode from battery percentage.
pub fn determine_mode(battery_percent: u8) -> EnergyMode {
    if battery_percent >= 50 {
        EnergyMode::Strategic
    } else if battery_percent >= 20 {
        EnergyMode::Reduced
    } else {
        EnergyMode::Silent
    }
}

/// Parse execution type from IPC payload value.
pub fn parse_execution_type(value: &str) -> Option<ExecutionType> {
    match value.trim().to_ascii_uppercase().as_str() {
        "LLM" => Some(ExecutionType::LLM),
        "PROACTIVE" => Some(ExecutionType::Proactive),
        "BACKGROUND_TASK" => Some(ExecutionType::BackgroundTask),
        "CRITICAL_REMINDER" => Some(ExecutionType::CriticalReminder),
        "VOICE" => Some(ExecutionType::Voice),
        _ => None,
    }
}

/// Authorize execution class under current energy mode.
pub fn authorize_execution(mode: &EnergyMode, execution: ExecutionType) -> EnergyDecision {
    match mode {
        EnergyMode::Strategic => EnergyDecision {
            allowed: true,
            reason: None,
        },
        EnergyMode::Reduced => match execution {
            ExecutionType::BackgroundTask => EnergyDecision {
                allowed: false,
                reason: Some("BACKGROUND_BLOCKED_REDUCED".to_string()),
            },
            ExecutionType::LLM => EnergyDecision {
                allowed: true,
                reason: Some("LLM_DOWNGRADED_REDUCED".to_string()),
            },
            ExecutionType::Proactive
            | ExecutionType::CriticalReminder
            | ExecutionType::Voice => EnergyDecision {
                allowed: true,
                reason: None,
            },
        },
        EnergyMode::Silent => match execution {
            ExecutionType::CriticalReminder | ExecutionType::Voice => EnergyDecision {
                allowed: true,
                reason: None,
            },
            ExecutionType::LLM => EnergyDecision {
                allowed: false,
                reason: Some("LLM_BLOCKED_SILENT".to_string()),
            },
            ExecutionType::Proactive => EnergyDecision {
                allowed: false,
                reason: Some("PROACTIVE_BLOCKED_SILENT".to_string()),
            },
            ExecutionType::BackgroundTask => EnergyDecision {
                allowed: false,
                reason: Some("BACKGROUND_BLOCKED_SILENT".to_string()),
            },
        },
    }
}

fn mode_rank(mode: &EnergyMode) -> u8 {
    match mode {
        EnergyMode::Strategic => 0,
        EnergyMode::Reduced => 1,
        EnergyMode::Silent => 2,
    }
}

fn max_mode(left: EnergyMode, right: EnergyMode) -> EnergyMode {
    if mode_rank(&left) >= mode_rank(&right) {
        left
    } else {
        right
    }
}

/// Single sampled energy snapshot from runtime observers.
#[derive(Clone, Copy, Debug)]
pub struct EnergySample {
    pub cpu_percent: f32,
    pub battery_percent: f32,
    pub thermal_celsius: f32,
    pub on_external_power: bool,
}

/// Derived runtime policy from the most recent sample.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct EnergyPolicy {
    pub llm_enabled: bool,
    pub proactive_enabled: bool,
    pub request_model_downgrade: bool,
    pub request_model_unload: bool,
    pub force_sleep: bool,
}

impl Default for EnergyPolicy {
    fn default() -> Self {
        Self {
            llm_enabled: true,
            proactive_enabled: true,
            request_model_downgrade: false,
            request_model_unload: false,
            force_sleep: false,
        }
    }
}

#[derive(Debug, Error)]
pub enum EnergyError {
    #[error("event bus error: {0}")]
    EventBus(#[from] EventBusError),
}

/// Authoritative energy manager that emits events only.
pub struct EnergyManager {
    config: EnergyConfig,
    policy: EnergyPolicy,
    forced_sleep_active: bool,
    thermal_recovery_counter: u8,
    thermal_recovery_active: bool,
}

impl EnergyManager {
    /// Create a new manager with explicit thresholds.
    pub fn new(config: EnergyConfig) -> Self {
        Self {
            config,
            policy: EnergyPolicy::default(),
            forced_sleep_active: false,
            thermal_recovery_counter: 0,
            thermal_recovery_active: false,
        }
    }

    /// Evaluate a sample and return emitted events plus derived policy.
    pub fn evaluate(&mut self, sample: EnergySample) -> (Vec<Event>, EnergyPolicy) {
        let mut events = Vec::new();
        let battery_low = sample.battery_percent <= self.config.battery_low_percent;
        let battery_critical = sample.battery_percent <= self.config.battery_critical_percent;
        let thermal_high = sample.thermal_celsius >= self.config.thermal_high_celsius;
        let thermal_critical = sample.thermal_celsius >= self.config.thermal_critical_celsius;
        let cpu_high = sample.cpu_percent >= self.config.cpu_high_percent;

        if battery_low {
            events.push(Event::BatteryLow);
        }
        if thermal_high {
            events.push(Event::ThermalHigh);
        }

        let battery_mode = determine_mode(sample.battery_percent.clamp(0.0, 100.0) as u8);
        let thermal_mode = self.evaluate_thermal_mode(thermal_high, thermal_critical);
        let cpu_mode = if cpu_high {
            EnergyMode::Reduced
        } else {
            EnergyMode::Strategic
        };
        let effective_mode = max_mode(max_mode(battery_mode, thermal_mode), cpu_mode);

        let request_model_downgrade = matches!(effective_mode, EnergyMode::Reduced | EnergyMode::Silent);
        let request_model_unload = matches!(effective_mode, EnergyMode::Silent);
        let llm_decision = authorize_execution(&effective_mode, ExecutionType::LLM);
        let proactive_decision = authorize_execution(&effective_mode, ExecutionType::Proactive);
        let force_sleep = matches!(effective_mode, EnergyMode::Silent)
            && (battery_critical || thermal_critical)
            && !sample.on_external_power;
        if force_sleep && !self.forced_sleep_active {
            events.push(Event::SleepEntered);
            self.forced_sleep_active = true;
        } else if !force_sleep && self.forced_sleep_active {
            events.push(Event::SleepExited);
            self.forced_sleep_active = false;
        }

        if request_model_downgrade {
            events.push(Event::ModelDowngrade);
        }
        if request_model_unload {
            events.push(Event::ModelUnload);
        }

        self.policy = EnergyPolicy {
            llm_enabled: llm_decision.allowed,
            proactive_enabled: proactive_decision.allowed && !force_sleep,
            request_model_downgrade,
            request_model_unload,
            force_sleep,
        };

        (events, self.policy)
    }

    /// Evaluate sample and publish resulting signals via event bus.
    pub fn evaluate_and_publish(
        &mut self,
        sample: EnergySample,
        event_bus: &EventBus,
        source: &str,
    ) -> Result<EnergyPolicy, EnergyError> {
        let (events, policy) = self.evaluate(sample);
        for event in events {
            event_bus.publish(event, source)?;
        }
        Ok(policy)
    }

    /// Return latest derived policy.
    pub fn policy(&self) -> EnergyPolicy {
        self.policy
    }

    fn evaluate_thermal_mode(&mut self, thermal_high: bool, thermal_critical: bool) -> EnergyMode {
        if thermal_critical {
            self.thermal_recovery_active = true;
            self.thermal_recovery_counter = 0;
            return EnergyMode::Silent;
        }

        if thermal_high {
            self.thermal_recovery_active = true;
            self.thermal_recovery_counter = 0;
            return EnergyMode::Reduced;
        }

        if self.thermal_recovery_active {
            let limit = self.config.thermal_recovery_cycles.max(1);
            if self.thermal_recovery_counter < limit {
                self.thermal_recovery_counter = self.thermal_recovery_counter.saturating_add(1);
                return EnergyMode::Reduced;
            }
            self.thermal_recovery_counter = 0;
            self.thermal_recovery_active = false;
        }

        EnergyMode::Strategic
    }
}

#[cfg(test)]
mod tests {
    use super::{
        authorize_execution, determine_mode, parse_execution_type, EnergyConfig, EnergyManager,
        EnergyMode, EnergySample, ExecutionType,
    };

    #[test]
    fn triggers_downgrade_under_pressure() {
        let mut manager = EnergyManager::new(EnergyConfig::default());
        let (events, policy) = manager.evaluate(EnergySample {
            cpu_percent: 80.0,
            battery_percent: 50.0,
            thermal_celsius: 40.0,
            on_external_power: false,
        });
        assert!(events
            .iter()
            .any(|event| matches!(event, crate::event_bus::Event::ModelDowngrade)));
        assert!(policy.request_model_downgrade);
    }

    #[test]
    fn determines_energy_modes() {
        assert_eq!(determine_mode(80), EnergyMode::Strategic);
        assert_eq!(determine_mode(35), EnergyMode::Reduced);
        assert_eq!(determine_mode(10), EnergyMode::Silent);
    }

    #[test]
    fn reduced_blocks_background_task() {
        let decision = authorize_execution(&EnergyMode::Reduced, ExecutionType::BackgroundTask);
        assert!(!decision.allowed);
    }

    #[test]
    fn reduced_allows_downgraded_llm() {
        let decision = authorize_execution(&EnergyMode::Reduced, ExecutionType::LLM);
        assert!(decision.allowed);
        assert_eq!(decision.reason.as_deref(), Some("LLM_DOWNGRADED_REDUCED"));
    }

    #[test]
    fn parse_execution_type_handles_unknown() {
        assert_eq!(parse_execution_type("LLM"), Some(ExecutionType::LLM));
        assert_eq!(parse_execution_type("UNKNOWN"), None);
    }
}
