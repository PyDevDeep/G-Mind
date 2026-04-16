from pydantic import BaseModel, ConfigDict, Field


class PubSubMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    # Base64 рядок від Google не буває мегабайтним. Обмежуємо до 5000 символів.
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
