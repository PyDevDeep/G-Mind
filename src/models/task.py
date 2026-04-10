import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin
from src.models.email import Email


class TaskStatusEnum(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    classified = "classified"
    generating_reply = "generating_reply"
    draft_created = "draft_created"
    completed = "completed"
    failed = "failed"


class ProcessingTask(Base, TimestampMixin):
    __tablename__ = "processing_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("emails.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[TaskStatusEnum] = mapped_column(
        Enum(TaskStatusEnum, name="task_status_enum", create_type=False),
        default=TaskStatusEnum.pending,
        nullable=False,
    )
    celery_task_id: Mapped[str] = mapped_column(String, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Відношення
    email: Mapped["Email"] = relationship()
