use apcos_os::energy_manager::{
    authorize_execution, determine_mode, EnergyConfig, EnergyManager, EnergyMode, EnergySample,
    ExecutionType,
};
use apcos_os::event_bus::Event;

#[test]
fn test_llm_downgrade_before_disable() {
    let reduced_decision = authorize_execution(&EnergyMode::Reduced, ExecutionType::LLM);
    assert!(reduced_decision.allowed);
    assert_eq!(
        reduced_decision.reason.as_deref(),
        Some("LLM_DOWNGRADED_REDUCED")
    );

    let silent_decision = authorize_execution(&EnergyMode::Silent, ExecutionType::LLM);
    assert!(!silent_decision.allowed);
    assert_eq!(silent_decision.reason.as_deref(), Some("LLM_BLOCKED_SILENT"));
}

#[test]
fn test_thermal_hysteresis_behavior() {
    let mut manager = EnergyManager::new(EnergyConfig {
        thermal_recovery_cycles: 2,
        ..EnergyConfig::default()
    });

    let hot = EnergySample {
        cpu_percent: 20.0,
        battery_percent: 80.0,
        thermal_celsius: 80.0,
        on_external_power: false,
    };
    let cool = EnergySample {
        cpu_percent: 20.0,
        battery_percent: 80.0,
        thermal_celsius: 45.0,
        on_external_power: false,
    };

    let (_events_hot, policy_hot) = manager.evaluate(hot);
    let (_events_cool_one, policy_cool_one) = manager.evaluate(cool);
    let (_events_cool_two, policy_cool_two) = manager.evaluate(cool);
    let (_events_cool_three, policy_cool_three) = manager.evaluate(cool);

    assert!(policy_hot.request_model_downgrade);
    assert!(policy_cool_one.request_model_downgrade);
    assert!(policy_cool_two.request_model_downgrade);
    assert!(!policy_cool_three.request_model_downgrade);
}

#[test]
fn test_graceful_transition_sequence() {
    let mut manager = EnergyManager::new(EnergyConfig::default());

    let strategic = manager.evaluate(EnergySample {
        cpu_percent: 15.0,
        battery_percent: 60.0,
        thermal_celsius: 40.0,
        on_external_power: false,
    });
    let reduced = manager.evaluate(EnergySample {
        cpu_percent: 15.0,
        battery_percent: 30.0,
        thermal_celsius: 40.0,
        on_external_power: false,
    });
    let silent = manager.evaluate(EnergySample {
        cpu_percent: 15.0,
        battery_percent: 15.0,
        thermal_celsius: 40.0,
        on_external_power: false,
    });

    let (_strategic_events, strategic_policy) = strategic;
    let (reduced_events, reduced_policy) = reduced;
    let (silent_events, silent_policy) = silent;

    assert_eq!(determine_mode(60), EnergyMode::Strategic);
    assert_eq!(determine_mode(30), EnergyMode::Reduced);
    assert_eq!(determine_mode(15), EnergyMode::Silent);

    assert!(strategic_policy.llm_enabled);
    assert!(!strategic_policy.request_model_downgrade);
    assert!(!strategic_policy.request_model_unload);

    assert!(reduced_policy.llm_enabled);
    assert!(reduced_policy.request_model_downgrade);
    assert!(!reduced_policy.request_model_unload);

    assert!(!silent_policy.llm_enabled);
    assert!(silent_policy.request_model_downgrade);
    assert!(silent_policy.request_model_unload);

    assert!(reduced_events
        .iter()
        .any(|event| matches!(event, Event::ModelDowngrade)));
    let downgrade_pos = silent_events
        .iter()
        .position(|event| matches!(event, Event::ModelDowngrade));
    let unload_pos = silent_events
        .iter()
        .position(|event| matches!(event, Event::ModelUnload));
    assert!(downgrade_pos.is_some());
    assert!(unload_pos.is_some());
    assert!(downgrade_pos < unload_pos);
}

