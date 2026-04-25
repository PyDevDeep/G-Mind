"""
Integration tests for WebhookService.process_notification edge cases.

Coverage (окремо від E2E happy path):
- first-ever notification (no prior historyId in Redis) → тільки set, без обробки
- history gap returns no messagesAdded → оновлює historyId, але email не зберігається
- DRAFT label → лист ігнорується, не зберігається в БД
- SENT label → лист ігнорується, не зберігається в БД
- Redis historyId оновлюється після обробки кожного виклику
"""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.schemas.webhook import GmailNotification
from src.services.webhook_service import WebhookService

pytestmark = pytest.mark.asyncio

FAKE_HISTORY_ID = 100


def _make_raw_msg(msg_id: str, label_ids: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": msg_id,
        "threadId": "thr-1",
        "labelIds": label_ids or ["INBOX"],
        "payload": {"headers": [{"name": "From", "value": "sender@test.com"}]},
    }


@pytest.fixture
def base_mocks() -> Generator[dict[str, Any], None, None]:
    """Базова фікстура: Redis + WatchService + EmailService замоковані."""
    mock_redis = MagicMock()
    mock_redis.set = AsyncMock(return_value=True)

    with (
        patch("src.services.webhook_service.redis_client", mock_redis),
        patch("src.services.queue_service.classify_email") as mock_celery,
        patch(
            "src.services.webhook_service.WatchService.check_history_gap"
        ) as mock_watch,
        patch("src.services.webhook_service.EmailService.get_message") as mock_get_msg,
        patch(
            "src.services.webhook_service.EmailService.parse_email_body",
            return_value="body text",
        ),
    ):
        mock_celery.delay = MagicMock()
        yield {
            "redis": mock_redis,
            "celery": mock_celery,
            "watch": mock_watch,
            "get_msg": mock_get_msg,
        }


class TestWebhookServiceFirstNotification:
    async def test_first_notification_no_history_id_sets_redis_and_returns(
        self, base_mocks: dict[str, Any]
    ) -> None:
        """Перша нотифікація (Redis порожній) — тільки зберігає historyId, без обробки листів."""
        base_mocks["redis"].get = AsyncMock(return_value=None)

        svc = WebhookService()
        await svc.process_notification(
            GmailNotification(emailAddress="user@test.com", historyId=FAKE_HISTORY_ID)
        )

        base_mocks["watch"].assert_not_called()
        base_mocks["celery"].delay.assert_not_called()
        base_mocks["redis"].set.assert_called_once()


class TestWebhookServiceEmptyHistory:
    async def test_no_messages_added_updates_history_id_only(
        self, base_mocks: dict[str, Any]
    ) -> None:
        """History gap не містить messagesAdded → historyId оновлюється, email не зберігається."""
        base_mocks["redis"].get = AsyncMock(return_value=str(FAKE_HISTORY_ID - 1))
        base_mocks["watch"].return_value = [{"labelsAdded": []}]  # без messagesAdded

        svc = WebhookService()
        await svc.process_notification(
            GmailNotification(emailAddress="user@test.com", historyId=FAKE_HISTORY_ID)
        )

        base_mocks["get_msg"].assert_not_called()
        base_mocks["celery"].delay.assert_not_called()
        base_mocks["redis"].set.assert_called()


class TestWebhookServiceLabelFiltering:
    @pytest.mark.parametrize("label", ["DRAFT", "SENT"])
    async def test_draft_and_sent_labels_ignored(
        self, base_mocks: dict[str, Any], label: str
    ) -> None:
        """Листи з labelIds DRAFT або SENT не зберігаються і не ставляться в чергу."""
        base_mocks["redis"].get = AsyncMock(return_value=str(FAKE_HISTORY_ID - 1))
        base_mocks["watch"].return_value = [
            {"messagesAdded": [{"message": {"id": "msg-skip"}}]}
        ]
        base_mocks["get_msg"].return_value = _make_raw_msg(
            "msg-skip", label_ids=[label]
        )

        with patch("src.services.webhook_service.QueueService") as MockQueue:
            queue_inst = AsyncMock()

            MockQueue.return_value = queue_inst

            svc = WebhookService()
            await svc.process_notification(
                GmailNotification(
                    emailAddress="user@test.com", historyId=FAKE_HISTORY_ID
                )
            )

            queue_inst.dispatch_email_processing.assert_not_awaited()

        base_mocks["celery"].delay.assert_not_called()


class TestWebhookServiceHistoryIdUpdate:
    async def test_history_id_always_updated_after_processing(
        self, base_mocks: dict[str, Any]
    ) -> None:
        """historyId в Redis оновлюється навіть якщо нових листів не було."""
        base_mocks["redis"].get = AsyncMock(return_value=str(FAKE_HISTORY_ID - 1))
        base_mocks["watch"].return_value = []  # порожня відповідь

        svc = WebhookService()
        await svc.process_notification(
            GmailNotification(emailAddress="user@test.com", historyId=FAKE_HISTORY_ID)
        )

        # Останній виклик set має містити новий historyId
        last_call_args = base_mocks["redis"].set.call_args_list[-1]
        assert str(FAKE_HISTORY_ID) in str(last_call_args)
