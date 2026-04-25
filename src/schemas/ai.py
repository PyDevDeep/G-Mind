import enum

from pydantic import BaseModel, ConfigDict, Field


class ClassificationCategory(enum.StrEnum):
    spam = "spam"
    needs_reply = "needs_reply"
    informational = "informational"
    urgent = "urgent"


class ClassificationResult(BaseModel):
    """Результат класифікації вхідного листа."""

    model_config = ConfigDict(extra="forbid", strict=True)

    category: ClassificationCategory = Field(description="Категорія листа")
    confidence_score: float = Field(
        ge=0.0, le=1.0, description="Впевненість моделі від 0.0 до 1.0"
    )
    reasoning: str = Field(
        ...,
        max_length=2000,
        description="Коротке логічне обґрунтування обраної категорії",
    )


class GeneratedReply(BaseModel):
    """Згенерована чернетка відповіді."""

    model_config = ConfigDict(extra="forbid", strict=True)

    subject: str = Field(..., max_length=1024, description="Тема листа-відповіді")
    # Cap email body at 50 000 characters to avoid oversized LLM prompts
    body: str = Field(
        ..., max_length=50000, description="Тіло листа-відповіді у форматі plain text"
    )
    tone: str = Field(
        ...,
        max_length=100,
        description="Тон, який було використано для відповіді (наприклад, 'professional', 'friendly')",
    )


class AIUsageStats(BaseModel):
    """Статистика використання LLM для трекінгу вартості."""

    model_config = ConfigDict(extra="forbid", strict=True)

    model_used: str = Field(..., max_length=255)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    processing_time_ms: int = Field(default=0, ge=0)
