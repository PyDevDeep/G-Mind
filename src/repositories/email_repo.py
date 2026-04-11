import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.email import Email
from src.models.task import ProcessingTask, TaskStatusEnum
from src.services.email_service import EmailService


class EmailRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def email_exists(self, message_id: str) -> bool:
        """Перевірка дедуплікації. Pub/Sub може надсилати один івенти кілька разів."""
        stmt = select(Email).where(Email.message_id == message_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def save_new_email_and_task(
        self, raw_msg: dict[str, Any], email_service: EmailService
    ) -> uuid.UUID:
        """Зберігає лист та створює початковий запис задачі в межах однієї транзакції."""

        payload: dict[str, Any] = raw_msg.get("payload", {})
        raw_headers: list[dict[str, Any]] = payload.get("headers", [])

        headers: dict[str, Any] = {h["name"].lower(): h["value"] for h in raw_headers}
        body = email_service.parse_email_body(payload)

        email = Email(
            message_id=raw_msg["id"],  # Використовуємо внутрішній ID Gmail
            thread_id=raw_msg["threadId"],
            subject=headers.get("subject"),
            sender=headers.get("from", "unknown"),
            recipient=headers.get("to", "unknown"),
            body=body,
            raw_payload=raw_msg,
            received_at=datetime.now(timezone.utc),
        )
        self.session.add(email)
        await self.session.flush()  # Отримуємо email.id

        task = ProcessingTask(email_id=email.id, status=TaskStatusEnum.pending)
        self.session.add(task)
        await self.session.commit()

        return email.id
