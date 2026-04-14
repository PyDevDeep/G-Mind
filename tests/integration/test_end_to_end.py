"""
File: tests/integration/test_end_to_end.py
Task: 3.4.1 - E2E Test Suite (Type-Safe)
"""

import uuid
from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.dependencies import async_session_maker
from src.models.task import TaskStatusEnum
from src.schemas.ai import AIUsageStats, ClassificationCategory, ClassificationResult
from src.schemas.webhook import GmailNotification
from src.services.storage_service import StorageService
from src.services.webhook_service import WebhookService
from src.services.worker_service import WorkerService

# Фіктивні дані
FAKE_EMAIL_ID = "fake-msg-123"
FAKE_THREAD_ID = "fake-thread-123"
FAKE_HISTORY_ID = 999999

pytestmark = pytest.mark.asyncio


def _make_raw_msg(msg_id: str, thread_id: str = FAKE_THREAD_ID) -> dict[str, Any]:
    return {
        "id": msg_id,
        "threadId": thread_id,
        "labelIds": ["INBOX"],
        "payload": {"headers": [{"name": "From", "value": "test@test.com"}]},
    }


@pytest.fixture
def mock_external_apis() -> Generator[dict[str, Any], None, None]:
    """Фікстура для мокання всіх зовнішніх мережевих запитів."""
    mock_redis = MagicMock()
    # get/set — async методи; get повертає попередній historyId — обробка проходить повний шлях
    mock_redis.get = AsyncMock(return_value=str(FAKE_HISTORY_ID - 1))
    mock_redis.set = AsyncMock(return_value=True)

    with (
        patch("src.services.webhook_service.redis_client", mock_redis),
        # Celery .delay() замокується — asyncio.run() всередині задачі конфліктує з pytest event loop
        patch("src.services.webhook_service.classify_email") as mock_celery_task,
        patch(
            "src.services.webhook_service.WatchService.check_history_gap"
        ) as mock_watch,
        patch("src.services.webhook_service.EmailService.get_message") as mock_get_msg,
        patch(
            "src.services.worker_service.EmailService.get_thread_messages"
        ) as mock_thread,
        patch("src.services.worker_service.EmailService.create_draft") as mock_draft,
        patch("src.services.worker_service.AIService.classify") as mock_classify,
        patch("src.services.worker_service.AIService.generate_reply") as mock_generate,
    ):
        mock_celery_task.delay = MagicMock()
        mock_thread.return_value = []
        mock_draft.return_value = "fake-draft-id-777"

        fake_stats = AIUsageStats(
            model_used="test-model", prompt_tokens=10, completion_tokens=10
        )

        yield {
            "watch": mock_watch,
            "get_msg": mock_get_msg,
            "thread": mock_thread,
            "draft": mock_draft,
            "classify": mock_classify,
            "generate": mock_generate,
            "stats": fake_stats,
            "redis": mock_redis,
            "celery_task": mock_celery_task,
        }


async def test_email_to_draft_happy_path(mock_external_apis: dict[str, Any]) -> None:
    """Перевіряє повний успішний ланцюг: Лист -> Класифікація (needs_reply) -> Генерація -> Чернетка."""
    mocks = mock_external_apis

    mocks["watch"].return_value = [
        {"messagesAdded": [{"message": {"id": FAKE_EMAIL_ID}}]}
    ]
    mocks["get_msg"].return_value = _make_raw_msg(FAKE_EMAIL_ID)
    mocks["classify"].return_value = (
        ClassificationResult(
            category=ClassificationCategory.needs_reply,
            confidence_score=0.9,
            reasoning="test",
        ),
        mocks["stats"],
    )
    mocks["generate"].return_value = (
        MagicMock(
            model_dump_json=lambda: '{"subject":"Re: test", "body":"hello", "tone":"pro"}'
        ),
        mocks["stats"],
    )

    # Крок 1: webhook реєструє лист і планує задачу (замокану)
    webhook_service = WebhookService()
    notification = GmailNotification(
        emailAddress="test@test.com", historyId=FAKE_HISTORY_ID
    )
    await webhook_service.process_notification(notification)

    # Отримуємо email_id з БД для подальших кроків
    async with async_session_maker() as session:
        storage = StorageService(session)
        email = await storage.get_email_by_message_id(FAKE_EMAIL_ID)
        assert email is not None
        email_id = str(email.id)

    # Кроки 2-4: виконуємо Celery-ланцюг напряму (без asyncio.run конфлікту)
    worker = WorkerService()
    await worker.process_classification(email_id)
    await worker.process_reply_generation(email_id)
    await worker.process_send_draft(email_id)

    # Перевіряємо фінальний стан
    async with async_session_maker() as session:
        storage = StorageService(session)
        email = await storage.get_email_by_message_id(FAKE_EMAIL_ID)
        assert email is not None
        task = await storage.get_task_by_email_id(email.id)
        assert task is not None
        assert task.status == TaskStatusEnum.draft_created

        ai_res = await storage.get_ai_response_by_task_id(task.id)
        assert ai_res is not None
        assert ai_res.classification == "needs_reply"
        assert ai_res.draft_id == "fake-draft-id-777"

    mocks["draft"].assert_called_once()


async def test_spam_email_no_draft(mock_external_apis: dict[str, Any]) -> None:
    """Перевіряє, що спам класифікується, але ланцюжок генерації зупиняється."""
    mocks = mock_external_apis
    spam_id = "spam-msg-001"

    mocks["watch"].return_value = [{"messagesAdded": [{"message": {"id": spam_id}}]}]
    mocks["get_msg"].return_value = _make_raw_msg(spam_id)
    mocks["classify"].return_value = (
        ClassificationResult(
            category=ClassificationCategory.spam,
            confidence_score=0.99,
            reasoning="is spam",
        ),
        mocks["stats"],
    )

    webhook_service = WebhookService()
    notification = GmailNotification(
        emailAddress="test@test.com", historyId=FAKE_HISTORY_ID + 1
    )
    await webhook_service.process_notification(notification)

    async with async_session_maker() as session:
        storage = StorageService(session)
        email = await storage.get_email_by_message_id(spam_id)
        assert email is not None
        email_id = str(email.id)

    # Виконуємо лише класифікацію — спам не потребує генерації
    worker = WorkerService()
    await worker.process_classification(email_id)

    async with async_session_maker() as session:
        storage = StorageService(session)
        email = await storage.get_email_by_message_id(spam_id)
        assert email is not None
        task = await storage.get_task_by_email_id(email.id)
        assert task is not None
        assert task.status == TaskStatusEnum.classified

    mocks["generate"].assert_not_called()
    mocks["draft"].assert_not_called()


async def test_duplicate_notification_ignored(
    mock_external_apis: dict[str, Any],
) -> None:
    """Перевіряє дедуплікацію: дві події з однаковим message_id обробляються один раз."""
    mocks = mock_external_apis
    dup_id = f"dup-msg-{uuid.uuid4().hex[:8]}"

    mocks["watch"].return_value = [{"messagesAdded": [{"message": {"id": dup_id}}]}]
    mocks["get_msg"].return_value = _make_raw_msg(dup_id)

    webhook_service = WebhookService()
    notification = GmailNotification(
        emailAddress="test@test.com", historyId=FAKE_HISTORY_ID + 2
    )

    # Перший виклик — лист реєструється
    await webhook_service.process_notification(notification)
    # Другий виклик — той самий message_id вже в БД, дедуплікація в storage відсікає
    await webhook_service.process_notification(notification)

    # get_message викликається лише раз (другий раз storage.get_email_by_message_id знаходить запис)
    mocks["get_msg"].assert_called_once()
    # classify_email.delay теж лише раз
    mocks["celery_task"].delay.assert_called_once()
