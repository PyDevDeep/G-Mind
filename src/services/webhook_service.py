import asyncio
from typing import Any

from src.dependencies import async_session_maker, redis_client
from src.repositories.email_repo import EmailRepository
from src.schemas.webhook import GmailNotification
from src.services.email_service import EmailService
from src.services.watch_service import WatchService
from src.utils.logging import get_logger
from src.workers.tasks import classify_email

logger = get_logger(__name__)


class WebhookService:
    def __init__(self) -> None:
        self.email_service = EmailService()
        self.watch_service = WatchService()

    async def process_notification(self, notification: GmailNotification) -> None:
        """Обробляє push-сповіщення: шукає нові листи та відправляє їх у Celery."""
        redis_key = f"gmail_history_id:{notification.emailAddress}"
        last_history_id = await redis_client.get(redis_key)

        # Якщо це перший запуск, просто зберігаємо ID і чекаємо наступних подій
        if not last_history_id:
            logger.info(
                "Відсутній попередній historyId. Зберігаємо поточний.",
                history_id=notification.historyId,
            )
            await redis_client.set(redis_key, str(notification.historyId))
            return

        # Запитуємо зміни через синхронний клієнт Google
        history_events: Any = await asyncio.to_thread(
            self.watch_service.check_history_gap, start_history_id=last_history_id
        )

        new_message_ids: set[str] = set()
        for event in history_events:
            if "messagesAdded" in event:
                for msg_added in event["messagesAdded"]:
                    new_message_ids.add(msg_added["message"]["id"])

        if not new_message_ids:
            logger.info(
                "Немає нових вхідних повідомлень (можливо це подія прочитання/видалення)"
            )
            await redis_client.set(redis_key, str(notification.historyId))
            return

        async with async_session_maker() as session:
            repo = EmailRepository(session)

            for msg_id in new_message_ids:
                if await repo.email_exists(msg_id):
                    logger.debug("Лист вже існує (дедуплікація)", message_id=msg_id)
                    continue

                raw_msg = await asyncio.to_thread(
                    self.email_service.get_message, msg_id
                )
                email_db_id = await repo.save_new_email_and_task(
                    raw_msg, self.email_service
                )

                logger.info(
                    "Відправка задачі в Celery",
                    email_id=str(email_db_id),
                    gmail_id=msg_id,
                )
                # Відправляємо задачу у фонову чергу Redis (ігноруємо false-positive від Pylance)
                classify_email.delay(str(email_db_id))  # type: ignore[attr-defined]

        # Оновлюємо маркер тільки після успішної обробки
        await redis_client.set(redis_key, str(notification.historyId))
