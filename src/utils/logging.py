"""
Logging System for Room Stager Agent

Simplified version based on kaufberater logging.
"""

import logging
import os
import sys
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import Optional

import structlog

# ═══════════════════════════════════════════════════════════════════════════════
# CORRELATION ID - Tracks entire request
# ═══════════════════════════════════════════════════════════════════════════════

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Get current correlation ID."""
    return _correlation_id.get()


def set_correlation_id(cid: Optional[str] = None) -> str:
    """Set correlation ID (generates new one if not provided)."""
    cid = cid or f"rs-{uuid.uuid4().hex[:8]}"
    _correlation_id.set(cid)
    return cid


def add_correlation_id(logger, method_name, event_dict):
    """Processor to add correlation ID to all log entries."""
    cid = get_correlation_id()
    if cid:
        event_dict["correlation_id"] = cid
    return event_dict


# ═══════════════════════════════════════════════════════════════════════════════
# STRUCTLOG CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

def setup_logging(
    level: Optional[str] = None,
    log_dir: Optional[str] = None,
    enable_file_logging: bool = False,
):
    """
    Configure logging system.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_dir: Directory for log files (default: ./logs)
        enable_file_logging: Enable file logging
    """
    log_level = level or os.getenv("LOG_LEVEL", "INFO")
    log_dir = log_dir or os.getenv("LOG_DIR", "./logs")
    is_json = os.getenv("LOG_FORMAT", "console").lower() == "json"

    # Create log directory
    if enable_file_logging:
        Path(log_dir).mkdir(parents=True, exist_ok=True)

    # Handler setup
    handlers = [logging.StreamHandler(sys.stdout)]

    # Standard logging config
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper()),
        handlers=handlers,
        force=True,
    )

    # Choose renderer
    if is_json:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(
            colors=True,
            exception_formatter=structlog.dev.plain_traceback,
        )

    # Structlog configuration
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_correlation_id,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Create formatter
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_log_level,
        ],
    )

    # Apply formatter
    for handler in logging.root.handlers:
        handler.setFormatter(formatter)

    # Initialize correlation ID
    set_correlation_id()


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a logger for a module."""
    return structlog.get_logger(name)


# Default logger
logger = get_logger("room_stager")

__all__ = [
    "setup_logging",
    "get_logger",
    "logger",
    "get_correlation_id",
    "set_correlation_id",
]
