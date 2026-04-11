from typing import Any

from celery.signals import task_failure

from src.utils.logging import get_logger

logger = get_logger(__name__)


@task_failure.connect
def handle_task_failure(
    sender: Any = None,
    task_id: str | None = None,
    exception: BaseException | None = None,
    args: tuple[Any, ...] | None = None,
    kwargs: dict[str, Any] | None = None,
    traceback: Any = None,
    einfo: Any = None,
    **other: Any,
):
    """Ловить усі падіння тасків після вичерпання ретраїв. Dead-letter queue handler."""
    logger.error(
        "Celery task failed completely",
        task_name=sender.name if sender else "Unknown",
        task_id=task_id,
        error=str(exception),
    )
    # TODO: Write to failed_tasks table
