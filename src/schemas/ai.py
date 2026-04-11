import enum

from pydantic import BaseModel, Field


class ClassificationCategory(str, enum.Enum):
    spam = "spam"
    needs_reply = "needs_reply"
    informational = "informational"
    urgent = "urgent"


class ClassificationResult(BaseModel):
    """Результат класифікації вхідного листа."""

    category: ClassificationCategory = Field(description="Категорія листа")
    confidence_score: float = Field(
        ge=0.0, le=1.0, description="Впевненість моделі від 0.0 до 1.0"
    )
    reasoning: str = Field(
        description="Коротке логічне обґрунтування обраної категорії"
    )


class GeneratedReply(BaseModel):
    """Згенерована чернетка відповіді."""

    subject: str = Field(description="Тема листа-відповіді")
    body: str = Field(description="Тіло листа-відповіді у форматі plain text")
    tone: str = Field(
        description="Тон, який було використано для відповіді (наприклад, 'professional', 'friendly')"
    )


class AIUsageStats(BaseModel):
    """Статистика використання LLM для трекінгу вартості."""

    model_used: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    processing_time_ms: int = 0
