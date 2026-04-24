import asyncio
import json
import time
import uuid
from typing import Any

from src.dependencies import async_session_maker
from src.models.task import TaskStatusEnum
from src.schemas.ai import ClassificationCategory, ClassificationResult
from src.services.ai_service import AIService
from src.services.email_service import EmailService
from src.services.storage_service import StorageService
from src.utils.logging import get_logger
from src.utils.metrics import CLASSIFICATION_LATENCY, EMAILS_PROCESSED

logger = get_logger(__name__)


class WorkerService:
    def __init__(self):
        self.ai_service = AIService()

    async def process_classification(self, email_id: str) -> dict[str, Any]:
        """Classify an email with AI and persist the result; returns category and task ID."""
        async with async_session_maker() as session:
            storage = StorageService(session)
            u_email_id = uuid.UUID(email_id)

            email = await storage.get_email(u_email_id)
            task = await storage.get_task_by_email_id(u_email_id)

            if not email or not task:
                raise ValueError(f"Entity not found: {email_id}")

            await storage.update_task_status(task.id, TaskStatusEnum.processing)

            start_time = time.perf_counter()
            try:
                classification, stats = await asyncio.to_thread(
                    self.ai_service.classify, email.body or email.subject or ""
                )
            finally:
                CLASSIFICATION_LATENCY.observe(time.perf_counter() - start_time)

            await storage.upsert_ai_response(
                task_id=task.id,
                classification=classification.category.value,
                confidence=classification.confidence_score,
                stats=stats,
            )
            await storage.update_task_status(task.id, TaskStatusEnum.classified)
            await session.commit()

            if classification.category.value != "needs_reply":
                EMAILS_PROCESSED.labels(status=classification.category.value).inc()

            return {"category": classification.category.value, "task_id": str(task.id)}

    async def process_reply_generation(self, email_id: str) -> dict[str, Any]:
        """Generate an AI reply draft and persist the result; returns task ID."""
        async with async_session_maker() as session:
            storage = StorageService(session)
            u_email_id = uuid.UUID(email_id)

            email = await storage.get_email(u_email_id)
            task = await storage.get_task_by_email_id(u_email_id)

            if not email or not task:
                raise ValueError("Not found")

            email_service = EmailService()
            thread_messages = await asyncio.to_thread(
                email_service.get_thread_messages, email.thread_id
            )

            res = await storage.get_ai_response_by_task_id(task.id)
            if not res:
                raise ValueError("AI Response not found")

            classification = ClassificationResult(
                category=ClassificationCategory(res.classification),
                confidence_score=res.confidence_score,
                reasoning="Retrieved from DB",
            )

            reply, stats = await asyncio.to_thread(
                self.ai_service.generate_reply,
                email.body or email.subject or "",
                thread_messages,
                classification,
            )

            await storage.upsert_ai_response(
                task_id=task.id,
                classification=classification.category.value,
                confidence=classification.confidence_score,
                stats=stats,
                generated_reply=reply.model_dump_json(),
            )
            await storage.update_task_status(task.id, TaskStatusEnum.generating_reply)
            await session.commit()
            return {"task_id": str(task.id)}

    async def process_send_draft(self, email_id: str) -> dict[str, Any]:
        """Create a Gmail draft from the stored AI reply; returns draft ID."""
        async with async_session_maker() as session:
            storage = StorageService(session)
            u_email_id = uuid.UUID(email_id)

            email = await storage.get_email(u_email_id)
            task = await storage.get_task_by_email_id(u_email_id)

            if not email or not task:
                raise ValueError("Not found")

            res = await storage.get_ai_response_by_task_id(task.id)
            if not res or not res.generated_reply:
                raise ValueError("No reply data")

            reply_data: dict[str, Any] = json.loads(res.generated_reply)

            email_service = EmailService()
            draft_id = await asyncio.to_thread(
                email_service.create_draft,
                to=email.sender,
                subject=reply_data.get("subject", "Re:"),
                body=reply_data.get("body", ""),
                thread_id=email.thread_id,
            )

            await storage.update_task_completed(task.id, draft_id)
            await session.commit()

            EMAILS_PROCESSED.labels(status="draft_created").inc()
            return {"draft_id": draft_id}

    async def process_task_failure(
        self, email_id: str, exception: Exception, stack_trace: str
    ) -> None:
        """Record a task failure in the database after all retries are exhausted."""
        async with async_session_maker() as session:
            storage = StorageService(session)
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
