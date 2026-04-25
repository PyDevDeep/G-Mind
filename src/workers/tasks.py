"""Celery task definitions for the email processing pipeline.

Changes vs original:
- classify_email chains to generate_ai_reply for BOTH 'needs_reply' AND 'urgent'
- asyncio loop handling via get/create pattern for thread-pool safety
"""

import asyncio
import uuid
from collections.abc import Coroutine
from typing import Any, TypeVar

from celery import Task

from src.services.worker_service import WorkerService
from src.utils.logger import bind_correlation_id, get_logger
from src.workers.celery_app import celery_app

_T = TypeVar("_T")

logger = get_logger(__name__)


class LLMRateLimitError(Exception):
    pass


class GmailAPIError(Exception):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_async(coro: Coroutine[Any, Any, _T]) -> _T:
    """Run a coroutine safely regardless of whether a loop already exists.

    Under `-P threads` each thread may or may not have a running loop.
    `asyncio.run()` always creates a fresh loop, which is fine for threads
    but will crash under prefork if a loop is already running.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Unlikely in Celery threads, but safe fallback
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


# Categories that trigger reply generation
_REPLY_CATEGORIES = frozenset({"needs_reply", "urgent"})


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


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
        result: dict[str, Any] = _run_async(service.process_classification(email_id))

        category = result.get("category")
        if category in _REPLY_CATEGORIES:
            logger.info(
                "Email requires reply, scheduling generate_ai_reply",
                category=category,
            )
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
        _run_async(service.process_reply_generation(email_id))

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
        result: dict[str, Any] = _run_async(service.process_send_draft(email_id))

        logger.info("Pipeline completed successfully", draft_id=result.get("draft_id"))
        return {
            "status": "draft_created",
            "email_id": email_id,
            "draft_id": result.get("draft_id"),
        }
    except Exception as e:
        logger.error("Draft creation failed", error=str(e))
        raise


# ---------------------------------------------------------------------------
# Periodic tasks (executed by celery-beat)
# ---------------------------------------------------------------------------


@celery_app.task(  # type: ignore[misc]
    bind=True,
    autoretry_for=(GmailAPIError,),
    retry_backoff=300,
    max_retries=3,
)
def renew_gmail_watch(self: Task):
    """Renew Gmail push-notification subscription before the 7-day expiry.

    Scheduled by celery-beat every 6 days (see celery_app.conf.beat_schedule).
    """
    from src.services.watch_service import WatchService

    logger.info("Periodic task: renewing Gmail watch() subscription")

    try:
        service = WatchService()
        result = service.renew_watch()
        logger.info(
            "Gmail watch renewed successfully",
            history_id=result.get("historyId"),
            expiration=result.get("expiration"),
        )
        return {"status": "renewed", "expiration": result.get("expiration")}
    except Exception as e:
        logger.error("Gmail watch renewal failed", error=str(e))
        raise
