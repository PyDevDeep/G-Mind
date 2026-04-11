import asyncio
import uuid
from typing import Any

from celery import Task

from src.services.worker_service import WorkerService
from src.utils.logging import bind_correlation_id, get_logger
from src.workers.celery_app import celery_app

logger = get_logger(__name__)


class LLMRateLimitError(Exception):
    """Викликається при 429 від OpenAI/Anthropic."""

    pass


class GmailAPIError(Exception):
    """Викликається при збоях Gmail API."""

    pass


@celery_app.task(  # type: ignore[misc]
    bind=True,
    autoretry_for=(LLMRateLimitError, GmailAPIError),
    retry_backoff=60,  # 60s, 120s, 240s...
    retry_backoff_max=900,
    max_retries=5,
)
def classify_email(
    self: Task, email_id: str, correlation_id: str | None = None
) -> dict[str, Any]:
    bind_correlation_id(correlation_id or str(uuid.uuid4()))
    logger.info("Початок класифікації листа", email_id=email_id)

    try:
        service = WorkerService()
        result = asyncio.run(service.process_classification(email_id))

        # Ланцюжок: Якщо лист потребує відповіді — плануємо наступну таску
        if result.get("category") == "needs_reply":
            logger.info("Лист потребує відповіді, планування generate_ai_reply")
            generate_ai_reply.delay(email_id, result, correlation_id)  # type: ignore

        return {"status": "classified", "email_id": email_id, "result": result}
    except Exception as e:
        logger.error("Помилка під час класифікації", error=str(e))
        raise


@celery_app.task(  # type: ignore[misc]
    bind=True,
    autoretry_for=(LLMRateLimitError, GmailAPIError),
    retry_backoff=60,
    max_retries=3,
)
def generate_ai_reply(
    self: Task,
    email_id: str,
    classification_data: dict[str, Any],
    correlation_id: str | None = None,
):
    bind_correlation_id(correlation_id)
    logger.info("Генерація AI відповіді", email_id=email_id)

    try:
        service = WorkerService()
        result = asyncio.run(service.process_reply_generation(email_id))

        logger.info("Відповідь згенерована, планування send_draft")
        send_draft.delay(email_id, result, correlation_id)  # type: ignore

        return {"status": "reply_generated", "email_id": email_id}
    except Exception as e:
        logger.error("Помилка під час генерації відповіді", error=str(e))
        raise


@celery_app.task(  # type: ignore[misc]
    bind=True,
    autoretry_for=(GmailAPIError,),
    retry_backoff=30,
    max_retries=3,
)
def send_draft(
    self: Task,
    email_id: str,
    reply_data: dict[str, Any],
    correlation_id: str | None = None,
):
    bind_correlation_id(correlation_id)
    logger.info("Створення чернетки Gmail", email_id=email_id)
    # TODO: Create Gmail DRAFT
    return {"status": "draft_created", "email_id": email_id}
