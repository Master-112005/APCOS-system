"""Centralized logging initialization for APCOS bootstrap."""

from __future__ import annotations

import logging
import os
import sys

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DEFAULT_LEVEL = "INFO"

_CONFIGURED = False


def configure_logging() -> None:
    """
    Configure process logging once with structured format.

    Environment override:
    - APCOS_LOG_LEVEL (e.g. DEBUG, INFO, WARNING, ERROR)
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    level_name = os.getenv("APCOS_LOG_LEVEL", DEFAULT_LEVEL).upper().strip()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(handler)

    audit_logger = logging.getLogger("apcos.audit")
    audit_logger.handlers.clear()
    audit_logger.setLevel(logging.INFO)
    audit_logger.propagate = False
    audit_handler = logging.StreamHandler(stream=sys.stdout)
    audit_handler.setLevel(logging.INFO)
    audit_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    audit_logger.addHandler(audit_handler)

    _CONFIGURED = True
