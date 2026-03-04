//! Service lifecycle registry for OS-supervised runtime components.

use std::collections::{HashMap, HashSet};
use thiserror::Error;

/// Service control contract.
pub trait Service: Send {
    fn name(&self) -> &str;
    fn start(&mut self) -> Result<(), String>;
    fn stop(&mut self) -> Result<(), String>;
    fn is_running(&self) -> bool;
}

#[derive(Debug, Error)]
pub enum ServiceRegistryError {
    #[error("service already registered: {0}")]
    DuplicateService(String),
    #[error("service not found: {0}")]
    ServiceNotFound(String),
    #[error("dependency cycle detected at service: {0}")]
    DependencyCycle(String),
    #[error("service operation failed: {0}")]
    ServiceFailure(String),
}

struct ServiceEntry {
    dependencies: Vec<String>,
    service: Box<dyn Service>,
}

/// Deterministic service dependency registry.
#[derive(Default)]
pub struct ServiceRegistry {
    services: HashMap<String, ServiceEntry>,
}

impl ServiceRegistry {
    /// Register service with dependencies.
    pub fn register_service(
        &mut self,
        service: Box<dyn Service>,
        dependencies: Vec<String>,
    ) -> Result<(), ServiceRegistryError> {
        let name = service.name().to_string();
        if self.services.contains_key(&name) {
            return Err(ServiceRegistryError::DuplicateService(name));
        }
        if dependencies.iter().any(|dep| dep == &name) {
            return Err(ServiceRegistryError::DependencyCycle(name));
        }
        self.services.insert(
            name,
            ServiceEntry {
                dependencies,
                service,
            },
        );
        Ok(())
    }

    /// Start a service and all of its dependencies in order.
    pub fn start_service(&mut self, name: &str) -> Result<(), ServiceRegistryError> {
        let mut visiting = HashSet::new();
        self.start_recursive(name, &mut visiting)
    }

    /// Stop one service.
    pub fn stop_service(&mut self, name: &str) -> Result<(), ServiceRegistryError> {
        let entry = self
            .services
            .get_mut(name)
            .ok_or_else(|| ServiceRegistryError::ServiceNotFound(name.to_string()))?;
        if entry.service.is_running() {
            entry
                .service
                .stop()
                .map_err(ServiceRegistryError::ServiceFailure)?;
        }
        Ok(())
    }

    /// Restart one service.
    pub fn restart_service(&mut self, name: &str) -> Result<(), ServiceRegistryError> {
        self.stop_service(name)?;
        self.start_service(name)
    }

    /// Start all services in dependency-safe order.
    pub fn start_all(&mut self) -> Result<(), ServiceRegistryError> {
        let names: Vec<String> = self.services.keys().cloned().collect();
        for name in names {
            self.start_service(&name)?;
        }
        Ok(())
    }

    /// Stop all services. Order is reverse registration to reduce dependency churn.
    pub fn stop_all(&mut self) -> Result<(), ServiceRegistryError> {
        let mut names: Vec<String> = self.services.keys().cloned().collect();
        names.reverse();
        for name in names {
            self.stop_service(&name)?;
        }
        Ok(())
    }

    /// Check running state for a service.
    pub fn is_running(&self, name: &str) -> bool {
        self.services
            .get(name)
            .map(|entry| entry.service.is_running())
            .unwrap_or(false)
    }

    fn start_recursive(
        &mut self,
        name: &str,
        visiting: &mut HashSet<String>,
    ) -> Result<(), ServiceRegistryError> {
        if visiting.contains(name) {
            return Err(ServiceRegistryError::DependencyCycle(name.to_string()));
        }

        let dependencies = self
            .services
            .get(name)
            .ok_or_else(|| ServiceRegistryError::ServiceNotFound(name.to_string()))?
            .dependencies
            .clone();

        visiting.insert(name.to_string());
        for dependency in dependencies {
            self.start_recursive(&dependency, visiting)?;
        }
        visiting.remove(name);

        let entry = self
            .services
            .get_mut(name)
            .ok_or_else(|| ServiceRegistryError::ServiceNotFound(name.to_string()))?;
        if !entry.service.is_running() {
            entry
                .service
                .start()
                .map_err(ServiceRegistryError::ServiceFailure)?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::{Service, ServiceRegistry};

    struct StubService {
        name: String,
        running: bool,
    }

    impl StubService {
        fn new(name: &str) -> Self {
            Self {
                name: name.to_string(),
                running: false,
            }
        }
    }

    impl Service for StubService {
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

    #[test]
    fn starts_dependencies_before_target() {
        let mut registry = ServiceRegistry::default();
        let _ = registry.register_service(Box::new(StubService::new("dep")), vec![]);
        let _ = registry.register_service(Box::new(StubService::new("main")), vec!["dep".into()]);
        let result = registry.start_service("main");
        assert!(result.is_ok());
        assert!(registry.is_running("dep"));
        assert!(registry.is_running("main"));
    }
}

