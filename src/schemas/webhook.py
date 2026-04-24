from pydantic import BaseModel, ConfigDict, Field


class PubSubMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    # Google's base64 payload is never large; cap at 5000 chars for safety
    data: str = Field(..., max_length=5000)
    messageId: str = Field(..., max_length=255)
    publishTime: str = Field(..., max_length=100)


class WebhookPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    message: PubSubMessage
    subscription: str = Field(..., max_length=512)


class GmailNotification(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    emailAddress: str = Field(..., max_length=255)
    historyId: int
