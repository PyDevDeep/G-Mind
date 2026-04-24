import asyncio
import uuid
from typing import Any

from celery import Task

from src.services.worker_service import WorkerService
from src.utils.logging import bind_correlation_id, get_logger
from src.workers.celery_app import celery_app

logger = get_logger(__name__)


class LLMRateLimitError(Exception):
    pass


class GmailAPIError(Exception):
    pass


@celery_app.task(  # type: ignore[misc]
    bind=True,
    autoretry_for=(LLMRateLimitError, GmailAPIError),
    retry_backoff=60,
    retry_backoff_max=900,
    max_retries=5,
)
def classify_email(self: Task, email_id: str, correlation_id: str | None = None):
    """Classify an incoming email and chain to reply generation if needed."""
    bind_correlation_id(correlation_id or str(uuid.uuid4()))
    logger.info("Starting email classification", email_id=email_id)

    try:
        service = WorkerService()
        result: dict[str, Any] = asyncio.run(service.process_classification(email_id))

        if result.get("category") == "needs_reply":
            logger.info("Email requires reply, scheduling generate_ai_reply")
            generate_ai_reply.delay(email_id, correlation_id)  # type: ignore

        return {"status": "classified", "email_id": email_id}
    except Exception as e:
        logger.error("Classification failed", error=str(e))
        raise


@celery_app.task(  # type: ignore[misc]
    bind=True,
    autoretry_for=(LLMRateLimitError, GmailAPIError),
    retry_backoff=60,
    max_retries=3,
)
def generate_ai_reply(self: Task, email_id: str, correlation_id: str | None = None):
    """Generate an AI reply for the email and chain to draft creation."""
    bind_correlation_id(correlation_id)
    logger.info("Generating AI reply", email_id=email_id)

    try:
        service = WorkerService()
        asyncio.run(service.process_reply_generation(email_id))

        logger.info("Reply generated, scheduling send_draft")
        send_draft.delay(email_id, correlation_id)  # type: ignore

        return {"status": "reply_generated", "email_id": email_id}
    except Exception as e:
        logger.error("Reply generation failed", error=str(e))
        raise


@celery_app.task(  # type: ignore[misc]
    bind=True,
    autoretry_for=(GmailAPIError,),
    retry_backoff=30,
    max_retries=3,
)
def send_draft(self: Task, email_id: str, correlation_id: str | None = None):
    """Create a Gmail draft from the generated reply, completing the pipeline."""
    bind_correlation_id(correlation_id)
    logger.info("Creating Gmail draft", email_id=email_id)

    try:
        service = WorkerService()
        result: dict[str, Any] = asyncio.run(service.process_send_draft(email_id))

        logger.info("Pipeline completed successfully", draft_id=result.get("draft_id"))
        return {
            "status": "draft_created",
            "email_id": email_id,
            "draft_id": result.get("draft_id"),
        }
    except Exception as e:
        logger.error("Draft creation failed", error=str(e))
        raise
