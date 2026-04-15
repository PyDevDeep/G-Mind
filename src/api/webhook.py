from fastapi import APIRouter, Header, Request

from src.schemas.webhook import WebhookPayload
from src.utils.limiter import limiter
from src.utils.logging import get_logger
from src.utils.pubsub import decode_pubsub_message

logger = get_logger(__name__)
router = APIRouter(tags=["Webhook"])


@router.post("/gmail")
@limiter.limit("60/minute")  # type: ignore[reportUntypedFunctionDecorator] # Жорсткий ліміт: 60 запитів на хвилину з одного IP
async def handle_gmail_notification(
    request: Request,  # КРИТИЧНО: Request має бути першим аргументом для slowapi
    payload: WebhookPayload,
    authorization: str | None = Header(default=None),
):
    """Ендпоінт для отримання push-сповіщень від Google Pub/Sub."""
    logger.info("Отримано webhook від Pub/Sub", message_id=payload.message.messageId)

    # 1. Verification (Заглушка)
    # verify_pubsub_token(authorization)

    try:
        # 2. Decode message
        notification = decode_pubsub_message(payload.message.data)
        logger.info(
            "Нова подія Gmail",
            history_id=notification.historyId,
            email=notification.emailAddress,
        )

        # Передаємо обробку оркестратору
        from src.services.webhook_service import WebhookService

        service = WebhookService()
        await service.process_notification(notification)

        # Завжди повертаємо 200 OK для immediate ack, щоб уникнути нескінченних ретраїв
        return {"status": "ok"}

    except ValueError as e:
        logger.error("Невалідний payload", error=str(e))
        # Навіть при невалідному форматі віддаємо 200, бо Pub/Sub не зможе це виправити ретраєм
        return {"status": "error", "detail": "Invalid payload"}
    except Exception as e:
        logger.error("Внутрішня помилка обробки вебхуку", error=str(e))
        # Віддаємо 500 тільки якщо впала наша БД/Redis і ми дійсно хочемо, щоб Google повторив запит
        return {"status": "error", "detail": "Internal server error"}
