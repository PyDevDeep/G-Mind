from typing import Any

from googleapiclient.errors import HttpError

from src.config import get_settings
from src.utils.gmail import GmailClient
from src.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class WatchService:
    def __init__(self):
        self.client = GmailClient()
        self.service = self.client.get_service()
        # Формування повного імені топіка для GCP
        self.topic_name = (
            f"projects/{settings.PUBSUB_PROJECT_ID}/topics/gmail-notifications"
        )

    def setup_watch(self, user_id: str = "me") -> dict[str, Any]:
        """Реєструє підписку на push-сповіщення Gmail для INBOX."""
        if not settings.PUBSUB_PROJECT_ID:
            logger.error("PUBSUB_PROJECT_ID не налаштовано в оточенні")
            raise ValueError("PUBSUB_PROJECT_ID is missing")

        request_body = {"labelIds": ["INBOX"], "topicName": self.topic_name}

        try:
            logger.info("Налаштування Gmail watch()", topic=self.topic_name)
            response = (
                self.service.users().watch(userId=user_id, body=request_body).execute()
            )
            logger.info(
                "Watch успішно налаштовано",
                history_id=response.get("historyId"),
                expiration=response.get("expiration"),
            )
            return response
        except HttpError as error:
            logger.error("Помилка налаштування watch", error=str(error))
            raise

    def renew_watch(self) -> dict[str, Any]:
        """Оновлює підписку (має викликатись кожні 6 днів)."""
        logger.info("Оновлення підписки Gmail watch")
        return self.setup_watch()

    def check_history_gap(
        self, start_history_id: str, user_id: str = "me"
    ) -> list[dict[str, Any]]:
        """Отримує список подій історії для перевірки пропущених повідомлень."""
        logger.info("Запит історії змін", start_history_id=start_history_id)
        try:
            response: dict[str, Any] = (
                self.service.users()
                .history()
                .list(userId=user_id, startHistoryId=start_history_id)
                .execute()
            )
            return response.get("history", [])
        except HttpError as error:
            # Помилка 404 зазвичай означає, що start_history_id застарів
            logger.error("Помилка отримання історії", error=str(error))
            return []
