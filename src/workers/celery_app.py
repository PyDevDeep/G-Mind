"""Celery application configuration.

Changes vs original:
- Added beat_schedule with 'renew-gmail-watch' job every 6 days (518400s)
"""

import time
from typing import Any

from celery import Celery, Task
from celery.signals import task_postrun, task_prerun, worker_ready
from prometheus_client import start_http_server

from src.config import get_settings
from src.utils.logger import bind_correlation_id, get_logger

logger = get_logger("celery_worker")
settings = get_settings()

# Explicit type for the global task-start-time registry
_task_start_times: dict[str, float] = {}

celery_app = Celery(
    "ai_email_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["src.workers.tasks", "src.workers.callbacks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    worker_send_task_events=True,
    task_send_sent_event=True,
)

# ---------------------------------------------------------------------------
# Beat schedule — periodic tasks executed by celery-beat
# ---------------------------------------------------------------------------
# Gmail watch() expires after 7 days max. Renew every 6 days for safety margin.
celery_app.conf.beat_schedule = {
    "renew-gmail-watch": {
        "task": "src.workers.tasks.renew_gmail_watch",
        "schedule": 518_400.0,  # 6 days in seconds
    },
}


@worker_ready.connect
def start_metrics_server(**kwargs: Any) -> None:
    """Start the Prometheus HTTP server for worker custom metrics."""
    start_http_server(8001)
    logger.info("Prometheus metrics server started on port 8001")


@task_prerun.connect
def on_task_prerun(
    task_id: str,
    task: Task,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    **others: Any,
) -> None:
    """Record task start time and bind correlation ID before each task runs."""
    correlation_id: str | None = kwargs.get("correlation_id")
    bind_correlation_id(correlation_id)

    _task_start_times[task_id] = time.perf_counter()

    logger.info("celery_task_started", task_name=task.name, celery_task_id=task_id)


@task_postrun.connect
def on_task_postrun(
    task_id: str,
    task: Task,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    retval: Any,
    state: str,
    **others: Any,
) -> None:
    """Log task completion and duration after each task finishes."""
    start_time: float | None = _task_start_times.pop(task_id, None)
    duration: float = 0.0

    if start_time is not None:
        duration = time.perf_counter() - start_time

    logger.info(
        "celery_task_completed",
        task_name=task.name,
        celery_task_id=task_id,
        status=state,
        duration=f"{duration:.4f}s",
    )
