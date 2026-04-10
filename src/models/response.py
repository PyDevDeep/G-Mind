import uuid

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin
from src.models.task import ProcessingTask


class AIResponse(Base, TimestampMixin):
    __tablename__ = "ai_responses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processing_tasks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    classification: Mapped[str] = mapped_column(String, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    generated_reply: Mapped[str] = mapped_column(String, nullable=True)
    draft_id: Mapped[str] = mapped_column(String, nullable=True)

    # Статистика використання
    model_used: Mapped[str] = mapped_column(String, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    processing_time_ms: Mapped[int] = mapped_column(Integer, default=0)

    # Відношення
    task: Mapped["ProcessingTask"] = relationship()
