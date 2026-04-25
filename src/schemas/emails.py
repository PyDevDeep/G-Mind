"""Pydantic schemas for Email API responses.

Roadmap requirement: src.schemas.emails.py — EmailCreate, EmailRead, EmailBrief
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EmailCreate(BaseModel):
    """Schema for creating an email record (internal use by webhook pipeline)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    message_id: str = Field(..., max_length=255)
    thread_id: str = Field(..., max_length=255)
    subject: str | None = Field(default=None, max_length=2000)
    sender: str = Field(..., max_length=500)
    recipient: str = Field(..., max_length=500)
    body: str | None = None
    received_at: datetime


class EmailRead(BaseModel):
    """Full email representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    message_id: str
    thread_id: str
    subject: str | None
    sender: str
    recipient: str
    body: str | None
    received_at: datetime
    created_at: datetime
    updated_at: datetime


class EmailBrief(BaseModel):
    """Compact email summary for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    message_id: str
    subject: str | None
    sender: str
    received_at: datetime
