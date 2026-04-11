import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.email import Email
from src.models.response import AIResponse
from src.models.task import ProcessingTask, TaskStatusEnum
from src.schemas.ai import AIUsageStats, ClassificationResult


class WorkerRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_email_and_task(
        self, email_id: str
    ) -> tuple[Email | None, ProcessingTask | None]:
        """Повертає лист та пов'язану з ним таску."""
        email_stmt = select(Email).where(Email.id == email_id)
        email = (await self.session.execute(email_stmt)).scalar_one_or_none()

        task_stmt = select(ProcessingTask).where(ProcessingTask.email_id == email_id)
        task = (await self.session.execute(task_stmt)).scalar_one_or_none()

        return email, task

    async def update_task_status(
        self, task_id: uuid.UUID, status: TaskStatusEnum
    ) -> None:
        """Оновлює статус виконання задачі."""
        stmt = select(ProcessingTask).where(ProcessingTask.id == task_id)
        task = (await self.session.execute(stmt)).scalar_one_or_none()
        if task:
            task.status = status
            await self.session.commit()

    async def save_classification_result(
        self,
        task_id: uuid.UUID,
        classification: ClassificationResult,
        stats: AIUsageStats,
    ) -> None:
        """Зберігає результат роботи AI та оновлює статус."""
        response = AIResponse(
            task_id=task_id,
            classification=classification.category.value,
            confidence_score=classification.confidence_score,
            reasoning=classification.reasoning,
            model_used=stats.model_used,
            prompt_tokens=stats.prompt_tokens,
            completion_tokens=stats.completion_tokens,
            processing_time_ms=stats.processing_time_ms,
        )
        self.session.add(response)

        stmt = select(ProcessingTask).where(ProcessingTask.id == task_id)
        task = (await self.session.execute(stmt)).scalar_one_or_none()
        if task:
            task.status = TaskStatusEnum.classified

        await self.session.commit()

    async def get_ai_response(self, task_id: uuid.UUID) -> AIResponse | None:
        """Отримує існуючий запис AIResponse для задачі."""
        stmt = select(AIResponse).where(AIResponse.task_id == task_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def update_reply_generation_result(
        self, task_id: uuid.UUID, generated_reply: str, stats: AIUsageStats
    ) -> None:
        """Зберігає текст згенерованої відповіді та акумулює статистику токенів."""
        response = await self.get_ai_response(task_id)
        if response:
            response.generated_reply = generated_reply
            response.prompt_tokens += stats.prompt_tokens
            response.completion_tokens += stats.completion_tokens
            response.processing_time_ms += stats.processing_time_ms

        stmt = select(ProcessingTask).where(ProcessingTask.id == task_id)
        task = (await self.session.execute(stmt)).scalar_one_or_none()
        if task:
            task.status = TaskStatusEnum.generating_reply

        await self.session.commit()
