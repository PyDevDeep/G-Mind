import logging
import os
import sys
from contextvars import ContextVar
from typing import Any, MutableMapping
from uuid import uuid4

import structlog

# Змінна контексту для зберігання ID поточного запиту
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    return correlation_id_var.get()


def bind_correlation_id(correlation_id: str | None = None) -> str:
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
    """Додає метадані контейнера для зручної фільтрації в Loki."""
    event_dict["service_name"] = os.getenv("SERVICE_NAME", "ai-email-assistant")
    event_dict["environment"] = os.getenv("ENVIRONMENT", "production")
    return event_dict


def configure_logging(log_level: str = "INFO", json_format: bool | None = None) -> None:
    # Примусово вмикаємо JSON у Docker, якщо не передано інше
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
        add_container_metadata,  # <--- Додано процесор метаданих
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json_format:
        processors.append(structlog.processors.JSONRenderer())  # type: ignore[arg-type]
    else:
        # Для локальної розробки кольоровий вивід зручніший
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
