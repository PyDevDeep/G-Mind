from fastapi import APIRouter, Header, Request

from src.schemas.webhook import WebhookPayload
from src.utils.limiter import limiter
from src.utils.logging import get_logger
from src.utils.pubsub import decode_pubsub_message

logger = get_logger(__name__)
router = APIRouter(tags=["Webhook"])


@router.post("/gmail")
@limiter.limit("60/minute")  # type: ignore[reportUntypedFunctionDecorator]
async def handle_gmail_notification(
    request: Request,  # Must be first argument for slowapi
    payload: WebhookPayload,
    authorization: str | None = Header(default=None),
):
    """Receive push notifications from Google Pub/Sub."""
    logger.info("Received webhook from Pub/Sub", message_id=payload.message.messageId)

    # TODO: verify_pubsub_token(authorization)

    try:
        notification = decode_pubsub_message(payload.message.data)
        logger.info(
            "New Gmail event",
            history_id=notification.historyId,
            email=notification.emailAddress,
        )

        from src.services.webhook_service import WebhookService

        service = WebhookService()
        await service.process_notification(notification)

        # Always return 200 to immediately ack; retries won't fix a bad payload
        return {"status": "ok"}

    except ValueError as e:
        logger.error("Invalid payload", error=str(e))
        # Return 200 even on bad format — Pub/Sub retries won't fix a malformed message
        return {"status": "error", "detail": "Invalid payload"}
    except Exception as e:
        logger.error("Internal webhook processing error", error=str(e))
        # Return 500 only for DB/Redis failures where we want Google to retry
        return {"status": "error", "detail": "Internal server error"}
