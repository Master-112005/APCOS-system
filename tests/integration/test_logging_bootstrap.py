from __future__ import annotations

import logging

from apcos.bootstrap import logging_config


def test_logging_initializes_once_and_format_matches(monkeypatch) -> None:
    monkeypatch.setattr(logging_config, "_CONFIGURED", False)
    root = logging.getLogger()
    root.handlers.clear()

    monkeypatch.setenv("APCOS_LOG_LEVEL", "INFO")
    logging_config.configure_logging()

    assert root.handlers
    handler_count = len(root.handlers)
    formatter = root.handlers[0].formatter
    assert formatter is not None
    assert formatter._fmt == "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

    logging_config.configure_logging()
    assert len(root.handlers) == handler_count
