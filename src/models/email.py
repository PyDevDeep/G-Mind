import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin


class Email(Base, TimestampMixin):
    __tablename__ = "emails"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    message_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    thread_id: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=True)
    sender: Mapped[str] = mapped_column(String, nullable=False)
    recipient: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(String, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Зберігаємо сирий payload від Gmail API для можливого дебагу
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_emails_message_id", "message_id"),
        Index("ix_emails_sender", "sender"),
        Index("ix_emails_received_at", "received_at"),
    )
