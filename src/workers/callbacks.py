import asyncio
from typing import Any

from celery.signals import task_failure

from src.services.worker_service import WorkerService
from src.utils.logging import get_logger

logger = get_logger(__name__)


@task_failure.connect
def handle_task_failure(
    sender: Any = None,
    task_id: str | None = None,
    exception: Exception | None = None,
    args: tuple[Any, ...] | None = None,
    kwargs: dict[str, Any] | None = None,
    traceback: Any = None,
    einfo: Any = None,
    **other: Any,
) -> None:
    """Ловить усі падіння тасків після вичерпання ретраїв. Dead-letter queue handler."""
    task_name: str = getattr(sender, "name", "Unknown")

    # Гарантуємо, що safe_exception завжди є екземпляром Exception для type checker'а
    safe_exception: Exception = (
        exception if exception is not None else Exception("Unknown error")
    )

    logger.error(
        "Celery task failed completely",
        task_name=task_name,
        celery_task_id=task_id,
        error=str(safe_exception),
    )

    email_id: Any = None
    if args and len(args) > 0:
        email_id = args[0]
    elif kwargs and "email_id" in kwargs:
        email_id = kwargs["email_id"]

    if not email_id:
        logger.error(
            "Dead-letter handler failed: Cannot extract email_id from args",
            args=args,
            kwargs=kwargs,
        )
        return

    stack_trace: str = str(einfo.traceback) if einfo else "No traceback available"

    try:
        service = WorkerService()
        asyncio.run(service.process_task_failure(email_id, safe_exception, stack_trace))
        logger.info("Падіння таски успішно зафіксовано в базі даних", email_id=email_id)
    except Exception as db_error:
        # Fallback логування, якщо лягла сама БД
        logger.critical(
            "Не вдалося записати failed_task у БД",
            error=str(db_error),
            original_error=str(safe_exception),
        )
