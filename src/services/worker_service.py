import asyncio

from src.dependencies import async_session_maker
from src.models.task import TaskStatusEnum
from src.repositories.worker_repo import WorkerRepository
from src.services.ai_service import AIService
from src.utils.logging import get_logger

logger = get_logger(__name__)


class WorkerService:
    def __init__(self):
        self.ai_service = AIService()

    async def process_classification(self, email_id: str) -> dict[str, str]:
        """Оркеструє процес класифікації листа."""
        async with async_session_maker() as session:
            repo = WorkerRepository(session)
            email, task = await repo.get_email_and_task(email_id)

            if not email or not task:
                raise ValueError(f"Дані для email_id {email_id} не знайдено в БД")

            await repo.update_task_status(task.id, TaskStatusEnum.processing)

            # Запускаємо синхронний мережевий виклик у thread pool, щоб не блокувати async loop
            logger.info("Виклик AIService.classify")
            classification, stats = await asyncio.to_thread(
                self.ai_service.classify, email.body or email.subject
            )

            await repo.save_classification_result(task.id, classification, stats)

            return {"category": classification.category.value, "task_id": str(task.id)}
