import asyncio

from src.dependencies import async_session_maker
from src.models.task import TaskStatusEnum
from src.repositories.worker_repo import WorkerRepository
from src.schemas.ai import ClassificationCategory, ClassificationResult
from src.services.ai_service import AIService
from src.services.email_service import EmailService
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

    async def process_reply_generation(self, email_id: str) -> dict[str, str]:
        """Оркеструє генерацію відповіді з використанням контексту гілки."""
        async with async_session_maker() as session:
            repo = WorkerRepository(session)
            email, task = await repo.get_email_and_task(email_id)

            if not email or not task:
                raise ValueError(f"Дані для email_id {email_id} не знайдено")

            ai_response = await repo.get_ai_response(task.id)
            if not ai_response:
                raise ValueError(
                    f"AIResponse для задачі {task.id} відсутній. Класифікація не була завершена."
                )

            # Відновлюємо об'єкт класифікації з БД для жорсткої типізації
            classification = ClassificationResult(
                category=ClassificationCategory(ai_response.classification),
                confidence_score=ai_response.confidence_score,
                reasoning="",
            )

            # Витягуємо контекст (синхронний мережевий виклик у thread)
            logger.info("Отримання контексту гілки", thread_id=email.thread_id)
            email_service = EmailService()
            thread_messages = await asyncio.to_thread(
                email_service.get_thread_messages, email.thread_id, limit=5
            )

            # Генерація відповіді
            logger.info("Виклик AIService.generate_reply")
            reply, stats = await asyncio.to_thread(
                self.ai_service.generate_reply,
                email.body or email.subject,
                thread_messages,
                classification,
            )

            await repo.update_reply_generation_result(
                task.id, reply.model_dump_json(), stats
            )

            return {"reply_json": reply.model_dump_json(), "task_id": str(task.id)}

    async def process_send_draft(self, email_id: str) -> dict[str, str]:
        """Створює чернетку в Gmail на основі згенерованої відповіді."""
        import json

        async with async_session_maker() as session:
            repo = WorkerRepository(session)
            email, task = await repo.get_email_and_task(email_id)

            if not email or not task:
                raise ValueError(f"Дані для email_id {email_id} не знайдено")

            ai_response = await repo.get_ai_response(task.id)
            if not ai_response or not ai_response.generated_reply:
                raise ValueError(f"Згенерована відповідь для задачі {task.id} відсутня")

            # Парсимо збережений JSON відповіді
            reply_data = json.loads(ai_response.generated_reply)

            logger.info("Виклик EmailService.create_draft")
            email_service = EmailService()

            # Синхронний мережевий виклик у thread
            draft_id: str = await asyncio.to_thread(
                email_service.create_draft,
                to=email.sender,
                subject=reply_data.get("subject", "Re:"),
                body=reply_data.get("body", ""),
                thread_id=email.thread_id,
            )

            await repo.update_task_completed(task.id, draft_id)

            return {"draft_id": draft_id, "task_id": str(task.id)}

    async def process_task_failure(
        self, email_id: str, exception: Exception, stack_trace: str
    ) -> None:
        """Передає критичну помилку в репозиторій."""
        async with async_session_maker() as session:
            repo = WorkerRepository(session)
            error_type = type(exception).__name__
            error_message = str(exception)
            await repo.log_task_failure(
                email_id, error_type, error_message, stack_trace
            )
