import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.models.base import Base
from src.models.task import ProcessingTask


class FailedTask(Base):
    __tablename__ = "failed_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processing_tasks.id", ondelete="CASCADE"), nullable=False
    )

    error_type: Mapped[str] = mapped_column(String, nullable=False)
    error_message: Mapped[str] = mapped_column(String, nullable=False)
    stack_trace: Mapped[str] = mapped_column(String, nullable=True)

    retry_exhausted: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Відношення
    task: Mapped["ProcessingTask"] = relationship()
