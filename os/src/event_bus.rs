//! Typed event bus for APCOS OS supervision.

use crossbeam_channel::{bounded, Receiver, RecvTimeoutError, Sender};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::{self, JoinHandle};
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use thiserror::Error;

/// Core supervisor events exchanged across the Rust OS layer.
#[derive(Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Event {
    IntentParsed,
    LifecycleValidated,
    TaskCreated,
    TaskCompleted,
    TaskArchived,
    BatteryLow,
    ThermalHigh,
    SleepEntered,
    SleepExited,
    IdentityChanged,
    ModelDowngrade,
    ModelUnload,
}

/// Event envelope carrying tracing and recursion metadata.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct EventEnvelope {
    pub id: u64,
    pub trace_id: u64,
    pub hop_count: u8,
    pub source: String,
    pub timestamp_ms: u128,
    pub event: Event,
}

/// Persistent event trace entry.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct EventTrace {
    pub id: u64,
    pub trace_id: u64,
    pub hop_count: u8,
    pub source: String,
    pub timestamp_ms: u128,
    pub event: Event,
}

#[derive(Debug, Error)]
pub enum EventBusError {
    #[error("event bus channel disconnected")]
    ChannelDisconnected,
    #[error("event recursion limit exceeded")]
    RecursionLimitExceeded,
    #[error("event bus already shutdown")]
    AlreadyShutdown,
}

#[derive(Clone)]
struct Subscriber {
    id: u64,
    handler: Arc<dyn Fn(EventEnvelope) + Send + Sync>,
}

enum BusCommand {
    Publish(EventEnvelope),
    Stop,
}

struct EventBusInner {
    tx: Sender<BusCommand>,
    subscribers: Mutex<HashMap<Event, Vec<Subscriber>>>,
    traces: Mutex<Vec<EventTrace>>,
    trace_capacity: usize,
    max_hops: u8,
    next_id: AtomicU64,
    active: Mutex<bool>,
    dispatch_thread: Mutex<Option<JoinHandle<()>>>,
}

/// Async publish/subscribe event bus with recursion protection.
#[derive(Clone)]
pub struct EventBus {
    inner: Arc<EventBusInner>,
}

impl EventBus {
    /// Create a new event bus with bounded queue, hop limit, and trace capacity.
    pub fn new(queue_capacity: usize, max_hops: u8, trace_capacity: usize) -> Self {
        let bounded_capacity = queue_capacity.max(1);
        let (tx, rx) = bounded::<BusCommand>(bounded_capacity);
        let inner = Arc::new(EventBusInner {
            tx,
            subscribers: Mutex::new(HashMap::new()),
            traces: Mutex::new(Vec::new()),
            trace_capacity: trace_capacity.max(1),
            max_hops: max_hops.max(1),
            next_id: AtomicU64::new(1),
            active: Mutex::new(true),
            dispatch_thread: Mutex::new(None),
        });

        let thread_inner = inner.clone();
        let handle = thread::spawn(move || dispatch_loop(thread_inner, rx));
        if let Ok(mut slot) = inner.dispatch_thread.lock() {
            *slot = Some(handle);
        }

        Self { inner }
    }

    /// Subscribe to a specific event type.
    pub fn subscribe<F>(&self, event: Event, handler: F) -> Result<u64, EventBusError>
    where
        F: Fn(EventEnvelope) + Send + Sync + 'static,
    {
        if !self.is_active() {
            return Err(EventBusError::AlreadyShutdown);
        }
        let id = self.next_id();
        let subscriber = Subscriber {
            id,
            handler: Arc::new(handler),
        };
        let mut map = self
            .inner
            .subscribers
            .lock()
            .map_err(|_| EventBusError::ChannelDisconnected)?;
        map.entry(event).or_default().push(subscriber);
        Ok(id)
    }

    /// Remove a subscription by id.
    pub fn unsubscribe(&self, subscription_id: u64) -> bool {
        let mut map = match self.inner.subscribers.lock() {
            Ok(guard) => guard,
            Err(_) => return false,
        };
        for subscribers in map.values_mut() {
            if let Some(index) = subscribers.iter().position(|entry| entry.id == subscription_id) {
                subscribers.remove(index);
                return true;
            }
        }
        false
    }

    /// Publish an event starting a fresh trace.
    pub fn publish(&self, event: Event, source: impl Into<String>) -> Result<u64, EventBusError> {
        let trace_id = self.next_id();
        self.publish_with_trace(event, source, trace_id, 0)?;
        Ok(trace_id)
    }

    /// Publish an event under an existing trace with explicit hop count.
    pub fn publish_with_trace(
        &self,
        event: Event,
        source: impl Into<String>,
        trace_id: u64,
        hop_count: u8,
    ) -> Result<(), EventBusError> {
        if !self.is_active() {
            return Err(EventBusError::AlreadyShutdown);
        }
        if hop_count > self.inner.max_hops {
            return Err(EventBusError::RecursionLimitExceeded);
        }

        let envelope = EventEnvelope {
            id: self.next_id(),
            trace_id,
            hop_count,
            source: source.into(),
            timestamp_ms: now_timestamp_ms(),
            event,
        };

        self.inner
            .tx
            .send(BusCommand::Publish(envelope))
            .map_err(|_| EventBusError::ChannelDisconnected)
    }

    /// Continue a trace with incremented hop count.
    pub fn continue_trace(
        &self,
        parent: &EventEnvelope,
        event: Event,
        source: impl Into<String>,
    ) -> Result<(), EventBusError> {
        let next_hop = parent.hop_count.saturating_add(1);
        self.publish_with_trace(event, source, parent.trace_id, next_hop)
    }

    /// Return a snapshot of recent traces.
    pub fn traces(&self) -> Vec<EventTrace> {
        match self.inner.traces.lock() {
            Ok(guard) => guard.clone(),
            Err(_) => Vec::new(),
        }
    }

    /// Gracefully shutdown dispatch thread.
    pub fn shutdown(&self) -> Result<(), EventBusError> {
        if !self.mark_inactive() {
            return Ok(());
        }

        self.inner
            .tx
            .send(BusCommand::Stop)
            .map_err(|_| EventBusError::ChannelDisconnected)?;

        let mut guard = self
            .inner
            .dispatch_thread
            .lock()
            .map_err(|_| EventBusError::ChannelDisconnected)?;
        if let Some(handle) = guard.take() {
            let _ = handle.join();
        }
        Ok(())
    }

    fn next_id(&self) -> u64 {
        self.inner.next_id.fetch_add(1, Ordering::Relaxed)
    }

    fn is_active(&self) -> bool {
        self.inner.active.lock().map(|v| *v).unwrap_or(false)
    }

    fn mark_inactive(&self) -> bool {
        match self.inner.active.lock() {
            Ok(mut active) => {
                if !*active {
                    return false;
                }
                *active = false;
                true
            }
            Err(_) => false,
        }
    }
}

impl Drop for EventBus {
    fn drop(&mut self) {
        // Only the final owner should drive shutdown. Cloned handles are used
        // by publishers/subscribers and must not stop the bus when dropped.
        if Arc::strong_count(&self.inner) == 1 {
            let _ = self.shutdown();
        }
    }
}

fn dispatch_loop(inner: Arc<EventBusInner>, rx: Receiver<BusCommand>) {
    loop {
        match rx.recv_timeout(Duration::from_millis(50)) {
            Ok(BusCommand::Publish(envelope)) => {
                if envelope.hop_count > inner.max_hops {
                    continue;
                }
                record_trace(&inner, &envelope);
                let handlers = matching_handlers(&inner, &envelope.event);
                for handler in handlers {
                    handler(envelope.clone());
                }
            }
            Ok(BusCommand::Stop) => break,
            Err(RecvTimeoutError::Timeout) => continue,
            Err(RecvTimeoutError::Disconnected) => break,
        }
    }
}

fn matching_handlers(
    inner: &Arc<EventBusInner>,
    event: &Event,
) -> Vec<Arc<dyn Fn(EventEnvelope) + Send + Sync>> {
    let map = match inner.subscribers.lock() {
        Ok(guard) => guard,
        Err(_) => return Vec::new(),
    };
    map.get(event)
        .map(|entries| entries.iter().map(|entry| entry.handler.clone()).collect())
        .unwrap_or_default()
}

fn record_trace(inner: &Arc<EventBusInner>, envelope: &EventEnvelope) {
    if let Ok(mut traces) = inner.traces.lock() {
        traces.push(EventTrace {
            id: envelope.id,
            trace_id: envelope.trace_id,
            hop_count: envelope.hop_count,
            source: envelope.source.clone(),
            timestamp_ms: envelope.timestamp_ms,
            event: envelope.event.clone(),
        });
        if traces.len() > inner.trace_capacity {
            let overflow = traces.len().saturating_sub(inner.trace_capacity);
            traces.drain(0..overflow);
        }
    }
}

fn now_timestamp_ms() -> u128 {
    match SystemTime::now().duration_since(UNIX_EPOCH) {
        Ok(duration) => duration.as_millis(),
        Err(_) => 0,
    }
}

#[cfg(test)]
mod tests {
    use super::{Event, EventBus};
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::Arc;
    use std::thread;
    use std::time::Duration;

    #[test]
    fn dispatches_subscribed_event() {
        let bus = EventBus::new(32, 4, 64);
        let hits = Arc::new(AtomicUsize::new(0));
        let hits_clone = hits.clone();
        let sub_result = bus.subscribe(Event::IntentParsed, move |_| {
            hits_clone.fetch_add(1, Ordering::SeqCst);
        });
        assert!(sub_result.is_ok());

        let publish_result = bus.publish(Event::IntentParsed, "test");
        assert!(publish_result.is_ok());
        thread::sleep(Duration::from_millis(40));
        assert_eq!(hits.load(Ordering::SeqCst), 1);
    }
}
