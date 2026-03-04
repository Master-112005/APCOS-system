//! Structured, thread-safe logging primitives for APCOS OS layer.

use chrono::Utc;
use std::io::{self, Write};
use std::sync::{Arc, Mutex};

/// Supported log levels for structured supervisor logging.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LogLevel {
    Info,
    Warning,
    Error,
    Critical,
}

impl LogLevel {
    fn as_str(self) -> &'static str {
        match self {
            LogLevel::Info => "INFO",
            LogLevel::Warning => "WARN",
            LogLevel::Error => "ERROR",
            LogLevel::Critical => "CRITICAL",
        }
    }
}

/// Thread-safe structured logger.
#[derive(Clone)]
pub struct StructuredLogger {
    component: String,
    sink: Arc<Mutex<Box<dyn Write + Send>>>,
}

impl StructuredLogger {
    /// Create a logger writing to stdout.
    pub fn new(component: impl Into<String>) -> Self {
        Self {
            component: component.into(),
            sink: Arc::new(Mutex::new(Box::new(io::stdout()))),
        }
    }

    /// Create a logger with a custom sink. Useful for tests and IPC adapters.
    pub fn with_sink(component: impl Into<String>, sink: Box<dyn Write + Send>) -> Self {
        Self {
            component: component.into(),
            sink: Arc::new(Mutex::new(sink)),
        }
    }

    /// Emit an info-level log line.
    pub fn info(&self, message: &str) -> io::Result<()> {
        self.log(LogLevel::Info, message)
    }

    /// Emit a warning-level log line.
    pub fn warn(&self, message: &str) -> io::Result<()> {
        self.log(LogLevel::Warning, message)
    }

    /// Emit an error-level log line.
    pub fn error(&self, message: &str) -> io::Result<()> {
        self.log(LogLevel::Error, message)
    }

    /// Emit a critical-level log line.
    pub fn critical(&self, message: &str) -> io::Result<()> {
        self.log(LogLevel::Critical, message)
    }

    /// Emit a structured log line with explicit level.
    pub fn log(&self, level: LogLevel, message: &str) -> io::Result<()> {
        let timestamp = Utc::now().to_rfc3339();
        let sanitized = sanitize_message(message);
        let line = format!(
            "{timestamp} | {} | {} | {sanitized}\n",
            level.as_str(),
            self.component
        );
        let mut sink = self
            .sink
            .lock()
            .map_err(|_| io::Error::other("log sink mutex poisoned"))?;
        sink.write_all(line.as_bytes())?;
        sink.flush()
    }
}

fn sanitize_message(message: &str) -> String {
    message.replace(['\n', '\r'], " ").trim().to_string()
}

#[cfg(test)]
mod tests {
    use super::{LogLevel, StructuredLogger};
    use std::io::{self, Write};
    use std::sync::{Arc, Mutex};

    #[derive(Clone, Default)]
    struct TestBuffer(Arc<Mutex<Vec<u8>>>);

    impl Write for TestBuffer {
        fn write(&mut self, buf: &[u8]) -> io::Result<usize> {
            let mut guard = self
                .0
                .lock()
                .map_err(|_| io::Error::other("buffer mutex poisoned"))?;
            guard.extend_from_slice(buf);
            Ok(buf.len())
        }

        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    #[test]
    fn structured_logger_formats_line() {
        let sink = TestBuffer::default();
        let view = sink.0.clone();
        let logger = StructuredLogger::with_sink("unit", Box::new(sink));

        let result = logger.log(LogLevel::Info, "message");
        assert!(result.is_ok());

        let output = String::from_utf8(
            view.lock()
                .map(|buf| buf.clone())
                .unwrap_or_else(|_| Vec::new()),
        )
        .unwrap_or_default();
        assert!(output.contains(" | INFO | unit | message"));
    }
}
