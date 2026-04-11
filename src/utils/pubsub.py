import base64
import json

from src.schemas.webhook import GmailNotification
from src.utils.logging import get_logger

logger = get_logger(__name__)


def verify_pubsub_token(token: str | None) -> bool:
    """
    Перевіряє OIDC токен від Google.
    Поки що залишаємо як заглушку. Для production тут потрібна інтеграція з google-auth.
    """
    if not token:
        logger.warning("Pub/Sub token відсутній")
        return False
    return True


def decode_pubsub_message(base64_data: str) -> GmailNotification:
    """Декодує base64 payload від Pub/Sub у Pydantic модель."""
    try:
        decoded_bytes = base64.b64decode(base64_data)
        decoded_str = decoded_bytes.decode("utf-8")
        payload = json.loads(decoded_str)
        return GmailNotification(**payload)
    except Exception as e:
        logger.error("Помилка декодування Pub/Sub повідомлення", error=str(e))
        raise ValueError("Invalid Pub/Sub payload") from e
