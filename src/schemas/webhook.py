from pydantic import BaseModel


class PubSubMessage(BaseModel):
    data: str
    messageId: str
    publishTime: str


class WebhookPayload(BaseModel):
    message: PubSubMessage
    subscription: str


class GmailNotification(BaseModel):
    emailAddress: str
    historyId: int
