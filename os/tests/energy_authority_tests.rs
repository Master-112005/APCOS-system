use apcos_os::energy_manager::{
    authorize_execution, determine_mode, parse_execution_type, EnergyMode, ExecutionType,
};

#[test]
fn test_mode_determination_strategic() {
    assert_eq!(determine_mode(80), EnergyMode::Strategic);
}

#[test]
fn test_mode_determination_reduced() {
    assert_eq!(determine_mode(35), EnergyMode::Reduced);
}

#[test]
fn test_mode_determination_silent() {
    assert_eq!(determine_mode(10), EnergyMode::Silent);
}

#[test]
fn test_strategic_allows_llm() {
    let decision = authorize_execution(&EnergyMode::Strategic, ExecutionType::LLM);
    assert!(decision.allowed);
}

#[test]
fn test_reduced_blocks_background() {
    let decision = authorize_execution(&EnergyMode::Reduced, ExecutionType::BackgroundTask);
    assert!(!decision.allowed);
}

#[test]
fn test_silent_blocks_proactive() {
    let decision = authorize_execution(&EnergyMode::Silent, ExecutionType::Proactive);
    assert!(!decision.allowed);
}

#[test]
fn test_no_unwrap_in_runtime_path() {
    let source = include_str!("../src/energy_manager.rs");
    assert!(!source.contains("unwrap("));
    assert!(!source.contains("expect("));
}

#[test]
fn test_no_panic_on_invalid_input() {
    let parsed = parse_execution_type("INVALID");
    assert!(parsed.is_none());
}

