use apcos_os::energy_manager::{EnergyConfig, EnergyManager, EnergySample};
use apcos_os::event_bus::{Event, EventBus};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::Duration;

#[test]
fn energy_thresholds_trigger_expected_events() {
    let bus = EventBus::new(128, 4, 256);
    let downgrade_hits = Arc::new(AtomicUsize::new(0));
    let unload_hits = Arc::new(AtomicUsize::new(0));

    let downgrade_clone = downgrade_hits.clone();
    let unload_clone = unload_hits.clone();

    let sub_one = bus.subscribe(Event::ModelDowngrade, move |_| {
        downgrade_clone.fetch_add(1, Ordering::SeqCst);
    });
    let sub_two = bus.subscribe(Event::ModelUnload, move |_| {
        unload_clone.fetch_add(1, Ordering::SeqCst);
    });
    assert!(sub_one.is_ok());
    assert!(sub_two.is_ok());

    let mut manager = EnergyManager::new(EnergyConfig::default());
    let result = manager.evaluate_and_publish(
        EnergySample {
            cpu_percent: 85.0,
            battery_percent: 8.0,
            thermal_celsius: 90.0,
            on_external_power: false,
        },
        &bus,
        "energy-test",
    );
    assert!(result.is_ok());

    thread::sleep(Duration::from_millis(80));
    assert!(downgrade_hits.load(Ordering::SeqCst) >= 1);
    assert!(unload_hits.load(Ordering::SeqCst) >= 1);
}

#[test]
fn energy_policy_downgrades_llm_before_disable() {
    let mut manager = EnergyManager::new(EnergyConfig::default());
    let (_events, policy) = manager.evaluate(EnergySample {
        cpu_percent: 76.0,
        battery_percent: 40.0,
        thermal_celsius: 50.0,
        on_external_power: false,
    });
    assert!(policy.llm_enabled);
    assert!(policy.request_model_downgrade);
    assert!(!policy.request_model_unload);
}
