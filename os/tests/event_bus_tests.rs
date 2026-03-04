use apcos_os::event_bus::{Event, EventBus};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

#[test]
fn event_dispatch_reaches_matching_subscriber() {
    let bus = EventBus::new(64, 4, 128);
    let hits = Arc::new(AtomicUsize::new(0));
    let hits_clone = hits.clone();

    let sub = bus.subscribe(Event::TaskCreated, move |_| {
        hits_clone.fetch_add(1, Ordering::SeqCst);
    });
    assert!(sub.is_ok());

    let publish = bus.publish(Event::TaskCreated, "test");
    assert!(publish.is_ok());

    thread::sleep(Duration::from_millis(60));
    assert_eq!(hits.load(Ordering::SeqCst), 1);
}

#[test]
fn event_bus_prevents_infinite_recursive_publish() {
    let bus = EventBus::new(128, 2, 256);
    let hits = Arc::new(AtomicUsize::new(0));
    let hits_clone = hits.clone();
    let bus_clone = bus.clone();

    let sub = bus.subscribe(Event::IntentParsed, move |envelope| {
        hits_clone.fetch_add(1, Ordering::SeqCst);
        let _ = bus_clone.continue_trace(&envelope, Event::IntentParsed, "loop-handler");
    });
    assert!(sub.is_ok());

    let publish = bus.publish(Event::IntentParsed, "seed");
    assert!(publish.is_ok());

    thread::sleep(Duration::from_millis(120));
    // hop_count: 0,1,2 are accepted, then limit stops recursion.
    assert_eq!(hits.load(Ordering::SeqCst), 3);
}

#[test]
fn event_bus_is_thread_safe_under_concurrent_publishers() {
    let bus = EventBus::new(2048, 4, 4096);
    let total = 8 * 100;
    let seen = Arc::new(AtomicUsize::new(0));
    let seen_clone = seen.clone();

    let sub = bus.subscribe(Event::ModelDowngrade, move |_| {
        seen_clone.fetch_add(1, Ordering::SeqCst);
    });
    assert!(sub.is_ok());

    let mut handles = Vec::new();
    for _ in 0..8 {
        let bus_clone = bus.clone();
        handles.push(thread::spawn(move || {
            for _ in 0..100 {
                let _ = bus_clone.publish(Event::ModelDowngrade, "publisher");
            }
        }));
    }

    for handle in handles {
        let _ = handle.join();
    }

    let deadline = Instant::now() + Duration::from_secs(2);
    while Instant::now() < deadline {
        if seen.load(Ordering::SeqCst) >= total {
            break;
        }
        thread::sleep(Duration::from_millis(20));
    }

    assert_eq!(seen.load(Ordering::SeqCst), total);
}

