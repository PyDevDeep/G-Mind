import logging
import os
import sys
from contextvars import ContextVar
from typing import Any, MutableMapping
from uuid import uuid4

import structlog

# Context variable holding the correlation ID for the current request/task
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Return the current correlation ID from context."""
    return correlation_id_var.get()


def bind_correlation_id(correlation_id: str | None = None) -> str:
    """Set the correlation ID for the current context; generate one if not provided."""
    if not correlation_id:
        correlation_id = str(uuid4())
    correlation_id_var.set(correlation_id)
    return correlation_id


def add_correlation_id(
    logger: logging.Logger, log_method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Structlog процесор для додавання correlation_id в усі логи."""
    req_id = get_correlation_id()
    if req_id:
        event_dict["correlation_id"] = req_id
    return event_dict


def add_container_metadata(
    logger: logging.Logger, log_method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Add container metadata fields to every log entry for Loki filtering."""
    event_dict["service_name"] = os.getenv("SERVICE_NAME", "ai-email-assistant")
    event_dict["environment"] = os.getenv("ENVIRONMENT", "production")
    return event_dict


def configure_logging(log_level: str = "INFO", json_format: bool | None = None) -> None:
    """Configure structlog with optional JSON output and container metadata processors."""
    # Force JSON in Docker if not explicitly overridden
    if json_format is None:
        json_format = os.getenv("LOG_JSON_FORMAT", "true").lower() == "true"

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )

    processors = [
        structlog.contextvars.merge_contextvars,
        add_correlation_id,
        add_container_metadata,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json_format:
        processors.append(structlog.processors.JSONRenderer())  # type: ignore[arg-type]
    else:
        # Use colored console output for local development
        processors.append(structlog.dev.ConsoleRenderer())  # type: ignore[arg-type]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Factory для створення логерів у модулях."""
    return structlog.get_logger(name)
