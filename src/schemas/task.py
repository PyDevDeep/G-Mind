"""Pydantic schemas for Task API responses.

Roadmap requirement: src/schemas/task.py — TaskCreate, TaskResponse, TaskStatusEnum
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from src.schemas.emails import EmailBrief


class TaskResponse(BaseModel):
    """Full task representation returned by GET /tasks/{id}."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email_id: uuid.UUID
    status: str
    celery_task_id: str | None
    retry_count: int
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    # Nested email summary (populated via relationship)
    email: EmailBrief | None = None


class TaskBrief(BaseModel):
    """Compact task summary for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email_id: uuid.UUID
    status: str
    retry_count: int
    created_at: datetime


class TaskRetryResponse(BaseModel):
    """Response after POST /tasks/{id}/retry."""

    task_id: uuid.UUID
    status: str
    message: str
