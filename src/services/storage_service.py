import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.email import Email
from src.models.failed_task import FailedTask
from src.models.response import AIResponse
from src.models.task import ProcessingTask, TaskStatusEnum
from src.schemas.ai import AIUsageStats


class StorageService:
    def __init__(self, session: AsyncSession):
        self.session = session

    # --- Email CRUD ---

    async def get_email(self, email_id: uuid.UUID) -> Optional[Email]:
        return await self.session.get(Email, email_id)

    async def get_email_by_message_id(self, message_id: str) -> Optional[Email]:
        stmt = select(Email).where(Email.message_id == message_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create_email(self, email_data: dict[str, Any]) -> Email:
        """Створює запис листа. Транзакція закривається ззовні або через flush."""
        email = Email(**email_data)
        if not email.received_at:
            email.received_at = datetime.now(timezone.utc)
        self.session.add(email)
        await self.session.flush()
        return email

    # --- Task CRUD ---

    async def create_task(self, email_id: uuid.UUID) -> ProcessingTask:
        task = ProcessingTask(email_id=email_id, status=TaskStatusEnum.pending)
        self.session.add(task)
        await self.session.flush()
        return task

    async def get_task_by_email_id(
        self, email_id: uuid.UUID
    ) -> Optional[ProcessingTask]:
        stmt = select(ProcessingTask).where(ProcessingTask.email_id == email_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def update_task_status(
        self,
        task_id: uuid.UUID,
        status: TaskStatusEnum,
        celery_id: Optional[str] = None,
    ) -> None:
        update_data: dict[str, Any] = {"status": status}
        if celery_id:
            update_data["celery_task_id"] = celery_id

        if status in [
            TaskStatusEnum.completed,
            TaskStatusEnum.failed,
            TaskStatusEnum.draft_created,
        ]:
            update_data["completed_at"] = datetime.now(timezone.utc)
        elif status == TaskStatusEnum.processing:
            update_data["started_at"] = datetime.now(timezone.utc)

        stmt = (
            update(ProcessingTask)
            .where(ProcessingTask.id == task_id)
            .values(**update_data)
        )
        await self.session.execute(stmt)

    async def update_task_completed(self, task_id: uuid.UUID, draft_id: str) -> None:
        """Зберігає ID чернетки та позначає задачу як завершену."""
        # Оновлюємо draft_id в AIResponse
        stmt_res = (
            update(AIResponse)
            .where(AIResponse.task_id == task_id)
            .values(draft_id=draft_id)
        )
        await self.session.execute(stmt_res)

        # Оновлюємо статус задачі
        await self.update_task_status(task_id, TaskStatusEnum.draft_created)
        await self.session.flush()

    # --- AI Response CRUD ---

    async def upsert_ai_response(
        self,
        task_id: uuid.UUID,
        classification: str,
        confidence: float,
        stats: AIUsageStats,
        generated_reply: Optional[str] = None,
        draft_id: Optional[str] = None,
    ) -> AIResponse:
        stmt = select(AIResponse).where(AIResponse.task_id == task_id)
        response = (await self.session.execute(stmt)).scalar_one_or_none()

        if not response:
            response = AIResponse(
                task_id=task_id,
                classification=classification,
                confidence_score=confidence,
                model_used=stats.model_used,
                prompt_tokens=stats.prompt_tokens,
                completion_tokens=stats.completion_tokens,
                processing_time_ms=stats.processing_time_ms,
                generated_reply=generated_reply,
                draft_id=draft_id,
            )
            self.session.add(response)
        else:
            response.classification = classification
            response.confidence_score = confidence
            response.generated_reply = generated_reply or response.generated_reply
            response.draft_id = draft_id or response.draft_id
            # Акумулюємо токени та час
            response.prompt_tokens += stats.prompt_tokens
            response.completion_tokens += stats.completion_tokens
            response.processing_time_ms += stats.processing_time_ms

        await self.session.flush()
        return response

    async def get_ai_response_by_task_id(
        self, task_id: uuid.UUID
    ) -> Optional[AIResponse]:
        """Отримує AIResponse за task_id з явною типізацією."""
        stmt = select(AIResponse).where(AIResponse.task_id == task_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # --- Failed Tasks ---

    async def create_failed_task(
        self,
        task_id: uuid.UUID,
        error_type: str,
        message: str,
        stack: Optional[str] = None,
    ) -> FailedTask:
        failed = FailedTask(
            task_id=task_id,
            error_type=error_type,
            error_message=message,
            stack_trace=stack,
            retry_exhausted=True,
        )
        self.session.add(failed)
        await self.session.flush()
        return failed

    async def get_ai_response(self, task_id: uuid.UUID) -> Optional[AIResponse]:
        stmt = select(AIResponse).where(AIResponse.task_id == task_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_failed_tasks(self, limit: int = 50) -> Sequence[FailedTask]:
        stmt = select(FailedTask).order_by(FailedTask.failed_at.desc()).limit(limit)
        return (await self.session.execute(stmt)).scalars().all()

    # --- Complex Orchestration ---

    async def save_incoming_email(
        self, email_data: dict[str, Any], raw_payload: dict[str, Any]
    ) -> uuid.UUID:
        """Атомарна операція: збереження листа + створення задачі."""
        email_data["raw_payload"] = raw_payload
        email = await self.create_email(email_data)
        await self.create_task(email.id)
        await self.session.commit()
        return email.id
