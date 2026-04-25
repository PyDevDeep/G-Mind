"""Queue service: deduplication via Redis lock and Celery task dispatch.

Extracted from WebhookService to satisfy SRP and roadmap requirement
for queue_service.py (roadmap rr.231-234, 686-693).
"""

import uuid
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.storage_service import StorageService
from src.utils.logger import get_logger
from src.workers.tasks import classify_email

logger = get_logger(__name__)

# Redis lock TTL in seconds — prevents duplicate processing if Pub/Sub
# delivers the same notification twice within this window.
_DEDUP_LOCK_TTL: int = 60


class QueueService:
    """Dispatch email processing tasks with Redis-based deduplication."""

    def __init__(self, session: AsyncSession, redis: Redis):
        self._storage = StorageService(session)
        self._redis = redis

    async def dispatch_email_processing(
        self,
        message_id: str,
        email_data: dict[str, Any],
        raw_payload: dict[str, Any],
        correlation_id: str | None = None,
    ) -> uuid.UUID | None:
        """Atomically deduplicate, persist, and dispatch a Celery task.

        Returns the DB email id on success, or None if the message was
        a duplicate (lock or DB).
        """
        lock_key = f"dedup:email:{message_id}"

        # 1. Redis lock — prevents race condition on concurrent Pub/Sub pushes
        acquired = await self._redis.set(lock_key, "1", nx=True, ex=_DEDUP_LOCK_TTL)
        if not acquired:
            logger.info("Duplicate suppressed by Redis lock", message_id=message_id)
            return None

        # 2. DB-level deduplication (covers restarts where lock expired)
        if await self._storage.get_email_by_message_id(message_id):
            logger.info("Duplicate suppressed by DB lookup", message_id=message_id)
            return None

        # 3. Persist email + create task atomically
        email_db_id = await self._storage.save_incoming_email(email_data, raw_payload)

        # 4. Dispatch Celery task
        classify_email.delay(str(email_db_id), correlation_id)  # type: ignore[attr-defined]

        logger.info(
            "Email registered and task dispatched",
            email_id=str(email_db_id),
            message_id=message_id,
        )
        return email_db_id

    async def get_queue_depth(self) -> int:
        """Return the approximate number of pending tasks in the Celery queue."""
        raw = await self._redis.llen("default")  # type: ignore[misc]
        return int(raw)  # type: ignore[arg-type]

    async def retry_failed_task(
        self,
        email_id: uuid.UUID,
        correlation_id: str | None = None,
    ) -> None:
        """Reset a failed task to pending and re-dispatch."""
        from src.models.task import TaskStatusEnum

        task = await self._storage.get_task_by_email_id(email_id)
        if not task:
            raise ValueError(f"No task found for email {email_id}")

        await self._storage.update_task_status(task.id, TaskStatusEnum.pending)
        classify_email.delay(str(email_id), correlation_id)  # type: ignore[attr-defined]
        logger.info("Failed task re-dispatched", email_id=str(email_id))
