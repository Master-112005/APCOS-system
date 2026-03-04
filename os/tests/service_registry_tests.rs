use apcos_os::runtime::service_registry::{Service, ServiceRegistry};
use std::sync::{Arc, Mutex};

struct RecordingService {
    name: String,
    running: bool,
    log: Arc<Mutex<Vec<String>>>,
}

impl RecordingService {
    fn new(name: &str, log: Arc<Mutex<Vec<String>>>) -> Self {
        Self {
            name: name.to_string(),
            running: false,
            log,
        }
    }
}

impl Service for RecordingService {
    fn name(&self) -> &str {
        &self.name
    }

    fn start(&mut self) -> Result<(), String> {
        self.running = true;
        if let Ok(mut guard) = self.log.lock() {
            guard.push(format!("start:{}", self.name));
        }
        Ok(())
    }

    fn stop(&mut self) -> Result<(), String> {
        self.running = false;
        if let Ok(mut guard) = self.log.lock() {
            guard.push(format!("stop:{}", self.name));
        }
        Ok(())
    }

    fn is_running(&self) -> bool {
        self.running
    }
}

#[test]
fn registry_starts_dependencies_before_dependents() {
    let log = Arc::new(Mutex::new(Vec::<String>::new()));
    let mut registry = ServiceRegistry::default();

    let dep = registry.register_service(
        Box::new(RecordingService::new("dep", log.clone())),
        vec![],
    );
    let main = registry.register_service(
        Box::new(RecordingService::new("main", log.clone())),
        vec!["dep".to_string()],
    );
    assert!(dep.is_ok());
    assert!(main.is_ok());

    let start = registry.start_service("main");
    assert!(start.is_ok());
    assert!(registry.is_running("dep"));
    assert!(registry.is_running("main"));

    let entries = log.lock().map(|guard| guard.clone()).unwrap_or_default();
    assert_eq!(entries.get(0), Some(&"start:dep".to_string()));
    assert_eq!(entries.get(1), Some(&"start:main".to_string()));
}

#[test]
fn registry_stops_and_restarts_service() {
    let log = Arc::new(Mutex::new(Vec::<String>::new()));
    let mut registry = ServiceRegistry::default();
    let reg = registry.register_service(
        Box::new(RecordingService::new("svc", log.clone())),
        vec![],
    );
    assert!(reg.is_ok());
    assert!(registry.start_service("svc").is_ok());
    assert!(registry.stop_service("svc").is_ok());
    assert!(registry.restart_service("svc").is_ok());
    assert!(registry.is_running("svc"));
}

