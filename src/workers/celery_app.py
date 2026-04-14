import time
from typing import Any, Dict, Optional, Tuple

from celery import Celery, Task
from celery.signals import task_postrun, task_prerun, worker_ready
from prometheus_client import start_http_server

from src.config import get_settings
from src.utils.logging import bind_correlation_id, get_logger

logger = get_logger("celery_worker")
settings = get_settings()

# Явна типізація глобального реєстру часу
_task_start_times: Dict[str, float] = {}

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
)


@worker_ready.connect
def start_metrics_server(**kwargs: Any) -> None:
    """Запускає Prometheus HTTP сервер для кастомних метрик воркера."""
    # Запускаємо сервер на порту 8001 всередині контейнера воркера
    start_http_server(8001)
    logger.info("Prometheus metrics server started on port 8001")


@task_prerun.connect
def on_task_prerun(
    task_id: str,
    task: Task,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    **others: Any,
) -> None:
    """Викликається перед запуском кожної таски з повною типізацією."""
    # Тепер Pylance знає, що це Optional[str]
    correlation_id: Optional[str] = kwargs.get("correlation_id")
    bind_correlation_id(correlation_id)

    _task_start_times[task_id] = time.perf_counter()

    logger.info("celery_task_started", task_name=task.name, celery_task_id=task_id)


@task_postrun.connect
def on_task_postrun(
    task_id: str,
    task: Task,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    retval: Any,
    state: str,
    **others: Any,
) -> None:
    """Викликається після завершення таски з повною типізацією."""
    start_time: Optional[float] = _task_start_times.pop(task_id, None)
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
