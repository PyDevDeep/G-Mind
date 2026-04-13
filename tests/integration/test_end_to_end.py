"""
File: tests/integration/test_end_to_end.py
Task: 3.4.1 - E2E Test Suite (Type-Safe)
"""

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.dependencies import async_session_maker
from src.models.task import TaskStatusEnum
from src.schemas.ai import AIUsageStats, ClassificationCategory, ClassificationResult
from src.schemas.webhook import GmailNotification
from src.services.storage_service import StorageService
from src.services.webhook_service import WebhookService

# Фіктивні дані
FAKE_EMAIL_ID = "fake-msg-123"
FAKE_THREAD_ID = "fake-thread-123"
FAKE_HISTORY_ID = 999999

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_external_apis() -> Generator[dict[str, Any], None, None]:
    """Фікстура для мокання всіх зовнішніх мережевих запитів."""
    with (
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
        # Налаштування базових відповідей
        mock_watch.return_value = [
            {"messagesAdded": [{"message": {"id": FAKE_EMAIL_ID}}]}
        ]
        mock_get_msg.return_value = {
            "id": FAKE_EMAIL_ID,
            "threadId": FAKE_THREAD_ID,
            "labelIds": ["INBOX"],
            "payload": {"headers": [{"name": "From", "value": "test@test.com"}]},
        }
        mock_thread.return_value = []
        mock_draft.return_value = "fake-draft-id-777"

        # Дефолтна статистика
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
        }


async def test_email_to_draft_happy_path(mock_external_apis: dict[str, Any]) -> None:
    """Перевіряє повний успішний ланцюг: Лист -> Класифікація (needs_reply) -> Генерація -> Чернетка."""
    mocks = mock_external_apis

    # Використовуємо Enum замість стрінгів
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
            model_dump_json=lambda: (
                '{"subject":"Re: test", "body":"hello", "tone":"pro"}'
            )
        ),
        mocks["stats"],
    )

    webhook_service = WebhookService()
    notification = GmailNotification(
        emailAddress="test@test.com", historyId=FAKE_HISTORY_ID
    )

    await webhook_service.process_notification(notification)

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

    # Використовуємо Enum
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
    mocks["get_msg"].return_value["id"] = "spam-msg-001"

    await webhook_service.process_notification(notification)

    async with async_session_maker() as session:
        storage = StorageService(session)
        email = await storage.get_email_by_message_id("spam-msg-001")
        assert email is not None  # Захист для Pylance

        task = await storage.get_task_by_email_id(email.id)
        assert task is not None  # Захист для Pylance
        assert task.status == TaskStatusEnum.classified

    mocks["generate"].assert_not_called()
    mocks["draft"].assert_not_called()


async def test_duplicate_notification_ignored(
    mock_external_apis: dict[str, Any],
) -> None:
    """Перевіряє дедуплікацію: дві події з однаковим message_id обробляються один раз."""
    mocks = mock_external_apis

    # Використовуємо Enum
    mocks["classify"].return_value = (
        ClassificationResult(
            category=ClassificationCategory.informational,
            confidence_score=0.8,
            reasoning="info",
        ),
        mocks["stats"],
    )

    webhook_service = WebhookService()
    notification = GmailNotification(
        emailAddress="test@test.com", historyId=FAKE_HISTORY_ID + 2
    )
    mocks["get_msg"].return_value["id"] = "dup-msg-999"

    await webhook_service.process_notification(notification)
    await webhook_service.process_notification(notification)

    mocks["get_msg"].assert_called_once()
    mocks["classify"].assert_called_once()
