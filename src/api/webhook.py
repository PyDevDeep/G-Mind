"""Gmail Pub/Sub webhook endpoint.

Changes vs original:
- WebhookService import moved to top level (no more lazy import anti-pattern)
- Internal errors now raise → FastAPI returns HTTP 500 → Pub/Sub retries
- ValueError still returns 200 (malformed payload, retry won't help)
- Correlation ID propagated to downstream services
"""

from fastapi import APIRouter, Header, Request

from src.schemas.webhook import WebhookPayload
from src.services.webhook_service import WebhookService
from src.utils.limiter import limiter
from src.utils.logging import get_correlation_id, get_logger
from src.utils.pubsub import decode_pubsub_message, verify_pubsub_token

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

    # Verify Pub/Sub OIDC token (stub will pass any non-empty token for now)
    if not verify_pubsub_token(authorization):
        logger.warning("Pub/Sub token verification failed")
        # Return 200 — bad auth is not retryable by Pub/Sub
        return {"status": "error", "detail": "Unauthorized"}

    try:
        notification = decode_pubsub_message(payload.message.data)
        logger.info(
            "New Gmail event",
            history_id=notification.historyId,
            email=notification.emailAddress,
        )

        service = WebhookService()
        await service.process_notification(
            notification,
            correlation_id=get_correlation_id(),
        )

        # Always return 200 to immediately ack
        return {"status": "ok"}

    except ValueError as e:
        logger.error("Invalid payload", error=str(e))
        # Return 200 — Pub/Sub retries won't fix a malformed message
        return {"status": "error", "detail": "Invalid payload"}

    except Exception:
        # Re-raise so FastAPI returns HTTP 500 — Pub/Sub WILL retry
        logger.exception("Internal webhook processing error")
        raise
