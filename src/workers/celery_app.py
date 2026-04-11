from celery import Celery

from src.config import get_settings

settings = get_settings()

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
    # Безпека виконання
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    # Маршрутизація (поки що все в дефолтній черзі, але готуємось до масштабування)
    task_default_queue="default",
)
