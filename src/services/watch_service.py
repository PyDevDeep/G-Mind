from typing import Any

from googleapiclient.errors import HttpError

from src.config import get_settings
from src.utils.gmail import GmailClient
from src.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


class WatchService:
    def __init__(self):
        self.client = GmailClient()
        self._service: Any | None = None
        # Full GCP Pub/Sub topic name required by the Gmail watch API
        self.topic_name = (
            f"projects/{settings.PUBSUB_PROJECT_ID}/topics/gmail-notifications"
        )

    @property
    def service(self) -> Any:
        """Return a lazily initialised authenticated Gmail API service."""
        if self._service is None:
            self._service = self.client.get_service()
        return self._service

    def setup_watch(self, user_id: str = "me") -> dict[str, Any]:
        """Register a Gmail push-notification subscription for INBOX."""
        if not settings.PUBSUB_PROJECT_ID:
            logger.error("PUBSUB_PROJECT_ID is not configured in the environment")
            raise ValueError("PUBSUB_PROJECT_ID is missing")

        request_body = {"labelIds": ["INBOX"], "topicName": self.topic_name}

        try:
            logger.info("Setting up Gmail watch()", topic=self.topic_name)
            response = (
                self.service.users().watch(userId=user_id, body=request_body).execute()
            )
            logger.info(
                "Gmail watch configured successfully",
                history_id=response.get("historyId"),
                expiration=response.get("expiration"),
            )
            return response
        except HttpError as error:
            logger.error("Failed to configure Gmail watch", error=str(error))
            raise

    def renew_watch(self) -> dict[str, Any]:
        """Renew the Gmail watch subscription (must be called every 6 days)."""
        logger.info("Renewing Gmail watch subscription")
        return self.setup_watch()

    def check_history_gap(
        self, start_history_id: str, user_id: str = "me"
    ) -> list[dict[str, Any]]:
        """Return history events since start_history_id to detect missed messages."""
        logger.info("Fetching history changes", start_history_id=start_history_id)
        try:
            response: dict[str, Any] = (
                self.service.users()
                .history()
                .list(userId=user_id, startHistoryId=start_history_id)
                .execute()
            )
            return response.get("history", [])
        except HttpError as error:
            # 404 typically means start_history_id is too old and was pruned
            logger.error("Failed to fetch history", error=str(error))
            return []
