//! Lightweight deterministic scheduler for OS-level housekeeping.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

/// Registered periodic task.
struct ScheduledTask {
    name: String,
    interval: Duration,
    next_run: Instant,
    action: Arc<dyn Fn() + Send + Sync>,
}

/// Cooperative periodic scheduler.
pub struct Scheduler {
    tasks: Arc<Mutex<Vec<ScheduledTask>>>,
    running: Arc<AtomicBool>,
    handle: Mutex<Option<JoinHandle<()>>>,
    tick: Duration,
}

impl Scheduler {
    /// Create a scheduler with a fixed tick interval.
    pub fn new(tick: Duration) -> Self {
        Self {
            tasks: Arc::new(Mutex::new(Vec::new())),
            running: Arc::new(AtomicBool::new(false)),
            handle: Mutex::new(None),
            tick: tick.max(Duration::from_millis(10)),
        }
    }

    /// Register a periodic task.
    pub fn register_task<F>(&self, name: impl Into<String>, interval: Duration, action: F) -> bool
    where
        F: Fn() + Send + Sync + 'static,
    {
        let mut tasks = match self.tasks.lock() {
            Ok(guard) => guard,
            Err(_) => return false,
        };
        let interval = interval.max(self.tick);
        let task = ScheduledTask {
            name: name.into(),
            interval,
            next_run: Instant::now() + interval,
            action: Arc::new(action),
        };
        tasks.push(task);
        true
    }

    /// Start scheduler loop.
    pub fn start(&self) -> bool {
        if self.running.swap(true, Ordering::SeqCst) {
            return true;
        }
        let tasks = self.tasks.clone();
        let running = self.running.clone();
        let tick = self.tick;
        let handle = thread::spawn(move || {
            while running.load(Ordering::SeqCst) {
                let now = Instant::now();
                if let Ok(mut guard) = tasks.lock() {
                    for task in guard.iter_mut() {
                        if now >= task.next_run {
                            (task.action)();
                            task.next_run = now + task.interval;
                        }
                    }
                }
                thread::sleep(tick);
            }
        });
        match self.handle.lock() {
            Ok(mut slot) => {
                *slot = Some(handle);
                true
            }
            Err(_) => false,
        }
    }

    /// Stop scheduler loop.
    pub fn stop(&self) -> bool {
        self.running.store(false, Ordering::SeqCst);
        match self.handle.lock() {
            Ok(mut slot) => {
                if let Some(handle) = slot.take() {
                    let _ = handle.join();
                }
                true
            }
            Err(_) => false,
        }
    }

    /// Return whether scheduler is running.
    pub fn is_running(&self) -> bool {
        self.running.load(Ordering::SeqCst)
    }

    /// Return registered task names.
    pub fn task_names(&self) -> Vec<String> {
        match self.tasks.lock() {
            Ok(guard) => guard.iter().map(|task| task.name.clone()).collect(),
            Err(_) => Vec::new(),
        }
    }
}

impl Drop for Scheduler {
    fn drop(&mut self) {
        let _ = self.stop();
    }
}

