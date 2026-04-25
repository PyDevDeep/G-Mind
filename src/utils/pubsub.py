"""Pub/Sub utilities: OIDC token verification and message decoding.

Changes vs original:
- verify_pubsub_token() now performs real Google OIDC JWT verification
  using google.oauth2.id_token + google.auth.transport.requests
- Verifies audience claim matches configured PUBSUB_AUDIENCE
- Falls back to permissive mode when PUBSUB_AUDIENCE is not configured (dev)
"""

import base64
import json

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from src.config import get_settings
from src.schemas.webhook import GmailNotification
from src.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


def verify_pubsub_token(token: str | None) -> bool:
    """Verify the OIDC bearer token attached by Google Pub/Sub push delivery.

    Google Pub/Sub sends an OIDC token in the Authorization header when push
    subscriptions are configured with a service account. This function validates:
    1. Token is present and is a valid JWT signed by Google
    2. The `aud` (audience) claim matches our configured endpoint URL

    In development (PUBSUB_AUDIENCE not set), logs a warning and accepts any
    non-empty token to avoid blocking local testing.
    """
    if not token:
        logger.warning("Pub/Sub token is missing")
        return False

    # Strip "Bearer " prefix if present
    if token.lower().startswith("bearer "):
        token = token[7:]

    audience = getattr(settings, "PUBSUB_AUDIENCE", None)

    if not audience:
        logger.warning(
            "PUBSUB_AUDIENCE not configured — skipping OIDC verification (dev mode)"
        )
        return True

    try:
        claim = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            audience=audience,
        )
        logger.info(
            "Pub/Sub OIDC token verified",
            email=claim.get("email"),
            audience=claim.get("aud"),
        )
        return True

    except ValueError as e:
        logger.warning("Pub/Sub OIDC token verification failed", error=str(e))
        return False


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
