"""Worker orchestration service for Celery tasks.

Each public method represents one step in the email processing pipeline:
classify → generate reply → send draft.
"""

import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession

from src.dependencies import async_session_maker
from src.models.email import Email
from src.models.task import ProcessingTask, TaskStatusEnum
from src.schemas.ai import ClassificationCategory, ClassificationResult
from src.services.ai_service import AIService
from src.services.email_service import EmailService
from src.services.storage_service import StorageService
from src.utils.logging import get_logger
from src.utils.metrics import CLASSIFICATION_LATENCY, EMAILS_PROCESSED

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers — eliminate DRY violations
# ---------------------------------------------------------------------------


class _EmailTaskPair(NamedTuple):
    email: Email
    task: ProcessingTask


@asynccontextmanager
async def _storage_session() -> AsyncIterator[tuple[StorageService, AsyncSession]]:
    """Yield a (StorageService, session) pair. Eliminates 4× boilerplate."""
    async with async_session_maker() as session:
        yield StorageService(session), session


async def _load_email_and_task(
    storage: StorageService, email_id: str
) -> _EmailTaskPair:
    """Load and validate an Email + ProcessingTask pair. Eliminates 3× boilerplate."""
    u_email_id = uuid.UUID(email_id)
    email = await storage.get_email(u_email_id)
    task = await storage.get_task_by_email_id(u_email_id)

    if not email or not task:
        raise ValueError(f"Email or task not found for id={email_id}")

    return _EmailTaskPair(email=email, task=task)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class WorkerService:
    """Orchestrates AI classification, reply generation, and draft creation."""

    def __init__(
        self,
        ai_service: AIService | None = None,
        email_service: EmailService | None = None,
    ):
        # Dependencies are injectable; defaults for backward compatibility.
        self.ai_service = ai_service or AIService()
        self.email_service = email_service or EmailService()

    async def process_classification(self, email_id: str) -> dict[str, Any]:
        """Classify an email with AI and persist the result; returns category and task ID."""
        async with _storage_session() as (storage, session):
            pair = await _load_email_and_task(storage, email_id)

            await storage.update_task_status(pair.task.id, TaskStatusEnum.processing)

            start_time = time.perf_counter()
            try:
                classification, stats = await asyncio.to_thread(
                    self.ai_service.classify,
                    pair.email.body or pair.email.subject or "",
                )
            finally:
                CLASSIFICATION_LATENCY.observe(time.perf_counter() - start_time)

            await storage.upsert_ai_response(
                task_id=pair.task.id,
                classification=classification.category.value,
                confidence=classification.confidence_score,
                stats=stats,
            )
            await storage.update_task_status(pair.task.id, TaskStatusEnum.classified)
            await session.commit()

            if classification.category.value != "needs_reply":
                EMAILS_PROCESSED.labels(status=classification.category.value).inc()

            return {
                "category": classification.category.value,
                "task_id": str(pair.task.id),
            }

    async def process_reply_generation(self, email_id: str) -> dict[str, Any]:
        """Generate an AI reply draft and persist the result; returns task ID."""
        async with _storage_session() as (storage, session):
            pair = await _load_email_and_task(storage, email_id)

            thread_messages = await asyncio.to_thread(
                self.email_service.get_thread_messages, pair.email.thread_id
            )

            res = await storage.get_ai_response_by_task_id(pair.task.id)
            if not res:
                raise ValueError("AI Response not found")

            classification = ClassificationResult(
                category=ClassificationCategory(res.classification),
                confidence_score=res.confidence_score,
                reasoning="Retrieved from DB",
            )

            reply, stats = await asyncio.to_thread(
                self.ai_service.generate_reply,
                pair.email.body or pair.email.subject or "",
                thread_messages,
                classification,
            )

            await storage.upsert_ai_response(
                task_id=pair.task.id,
                classification=classification.category.value,
                confidence=classification.confidence_score,
                stats=stats,
                generated_reply=reply.model_dump_json(),
            )
            await storage.update_task_status(
                pair.task.id, TaskStatusEnum.generating_reply
            )
            await session.commit()
            return {"task_id": str(pair.task.id)}

    async def process_send_draft(self, email_id: str) -> dict[str, Any]:
        """Create a Gmail draft from the stored AI reply; returns draft ID."""
        async with _storage_session() as (storage, session):
            pair = await _load_email_and_task(storage, email_id)

            res = await storage.get_ai_response_by_task_id(pair.task.id)
            if not res or not res.generated_reply:
                raise ValueError("No reply data")

            reply_data: dict[str, Any] = json.loads(res.generated_reply)

            draft_id = await asyncio.to_thread(
                self.email_service.create_draft,
                to=pair.email.sender,
                subject=reply_data.get("subject", "Re:"),
                body=reply_data.get("body", ""),
                thread_id=pair.email.thread_id,
            )

            await storage.update_task_completed(pair.task.id, draft_id)
            await session.commit()

            EMAILS_PROCESSED.labels(status="draft_created").inc()
            return {"draft_id": draft_id}

    async def process_task_failure(
        self, email_id: str, exception: Exception, stack_trace: str
    ) -> None:
        """Record a task failure in the database after all retries are exhausted."""
        async with _storage_session() as (storage, session):
            u_email_id = uuid.UUID(email_id)
            task = await storage.get_task_by_email_id(u_email_id)

            if not task:
                logger.error("Task not found for failure processing", email_id=email_id)
                return

            await storage.create_failed_task(
                task_id=task.id,
                error_type=type(exception).__name__,
                message=str(exception),
                stack=stack_trace,
            )
            await storage.update_task_status(task.id, TaskStatusEnum.failed)
            await session.commit()

            EMAILS_PROCESSED.labels(status="failed").inc()
