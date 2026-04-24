import asyncio

from src.dependencies import async_session_maker, redis_client
from src.schemas.webhook import GmailNotification
from src.services.email_service import EmailService
from src.services.storage_service import StorageService
from src.services.watch_service import WatchService
from src.utils.logging import get_logger
from src.workers.tasks import classify_email

logger = get_logger(__name__)


class WebhookService:
    def __init__(self):
        self.email_service = EmailService()
        self.watch_service = WatchService()

    async def process_notification(self, notification: GmailNotification) -> None:
        """Process a Gmail Pub/Sub notification: fetch new messages and dispatch Celery tasks."""
        redis_key = f"gmail_history_id:{notification.emailAddress}"
        last_history_id = await redis_client.get(redis_key)

        if not last_history_id:
            await redis_client.set(redis_key, str(notification.historyId))
            return

        history_events = await asyncio.to_thread(
            self.watch_service.check_history_gap, start_history_id=last_history_id
        )

        new_message_ids: set[str] = set()
        for event in history_events:
            if "messagesAdded" in event:
                for msg_added in event["messagesAdded"]:
                    new_message_ids.add(msg_added["message"]["id"])

        if not new_message_ids:
            await redis_client.set(redis_key, str(notification.historyId))
            return

        async with async_session_maker() as session:
            storage = StorageService(session)

            for msg_id in new_message_ids:
                # Skip already-processed messages (deduplication)
                if await storage.get_email_by_message_id(msg_id):
                    continue

                raw_msg = await asyncio.to_thread(
                    self.email_service.get_message, msg_id
                )

                # Skip drafts and sent mail to avoid processing our own outgoing messages
                label_ids = raw_msg.get("labelIds", [])
                if "DRAFT" in label_ids or "SENT" in label_ids:
                    continue

                headers = {
                    h["name"].lower(): h["value"]
                    for h in raw_msg["payload"].get("headers", [])
                }
                email_data = {
                    "message_id": raw_msg["id"],
                    "thread_id": raw_msg["threadId"],
                    "subject": headers.get("subject"),
                    "sender": headers.get("from", "unknown"),
                    "recipient": headers.get("to", "unknown"),
                    "body": self.email_service.parse_email_body(raw_msg["payload"]),
                }

                email_db_id = await storage.save_incoming_email(email_data, raw_msg)

                logger.info(
                    "Email registered, dispatching task", email_id=str(email_db_id)
                )
                classify_email.delay(str(email_db_id))  # type: ignore[attr-defined]

        await redis_client.set(redis_key, str(notification.historyId))
