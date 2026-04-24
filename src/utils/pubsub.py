import base64
import json

from src.schemas.webhook import GmailNotification
from src.utils.logging import get_logger

logger = get_logger(__name__)


def verify_pubsub_token(token: str | None) -> bool:
    """Verify the OIDC token from Google. Currently a stub — integrate google-auth for production."""
    if not token:
        logger.warning("Pub/Sub token is missing")
        return False
    return True


def decode_pubsub_message(base64_data: str) -> GmailNotification:
    """Decode a base64 Pub/Sub payload into a GmailNotification model."""
    try:
        decoded_bytes = base64.b64decode(base64_data)
        decoded_str = decoded_bytes.decode("utf-8")
        payload = json.loads(decoded_str)
        return GmailNotification(**payload)
    except Exception as e:
        logger.error("Failed to decode Pub/Sub message", error=str(e))
        raise ValueError("Invalid Pub/Sub payload") from e
