import uuid
from unittest.mock import patch

import pytest

from src.dependencies import async_session_maker
from src.models.task import TaskStatusEnum
from src.services.storage_service import StorageService
from src.services.worker_service import WorkerService
from src.workers.tasks import LLMRateLimitError

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def setup_failed_task_env():
    """Створює тестовий email та task для перевірки збоїв."""
    async with async_session_maker() as session:
        storage = StorageService(session)
        email = await storage.create_email(
            {
                "message_id": f"fail-test-msg-{uuid.uuid4().hex[:8]}",
                "thread_id": "fail-thread",
                "sender": "error@test.com",
                "recipient": "test@test.com",
                "subject": "Make me fail",
                "body": "crash now",
                "raw_payload": {},
            }
        )
        await storage.create_task(email.id)
        await session.commit()
        return str(email.id)


async def test_retry_on_llm_rate_limit(setup_failed_task_env: str):
    """Перевіряє, що WorkerService прокидає LLMRateLimitError при 429 від AI."""
    email_id = setup_failed_task_env

    with patch("src.services.worker_service.AIService.classify") as mock_classify:
        mock_classify.side_effect = LLMRateLimitError("OpenAI API limit exceeded")

        worker = WorkerService()
        with pytest.raises(LLMRateLimitError):
            await worker.process_classification(email_id)


async def test_dead_letter_after_max_retries(setup_failed_task_env: str):
    """Перевіряє запис помилки в БД через WorkerService.process_task_failure."""
    email_id = setup_failed_task_env
    exception = ValueError("Fatal DB Crash")

    worker = WorkerService()
    await worker.process_task_failure(email_id, exception, "No traceback available")

    async with async_session_maker() as session:
        storage = StorageService(session)

        task = await storage.get_task_by_email_id(uuid.UUID(email_id))
        assert task is not None
        assert task.status == TaskStatusEnum.failed

        failed_tasks = await storage.list_failed_tasks(limit=10)
        found = any(
            f.task_id == task.id and "Fatal DB Crash" in f.error_message
            for f in failed_tasks
        )
        assert found is True
