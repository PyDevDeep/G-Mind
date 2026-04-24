import os

from fastapi import Request
from slowapi import Limiter


def get_real_ip(request: Request) -> str:
    """Extract the real client IP, respecting X-Forwarded-For from proxies."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fallback for local development without a proxy
    return request.client.host if request.client else "127.0.0.1"


# Use Redis DB 1 for rate limits so it doesn't collide with Celery on DB 0
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
LIMITER_REDIS_URL = REDIS_URL[:-1] + "1" if REDIS_URL.endswith("/0") else REDIS_URL

limiter = Limiter(
    key_func=get_real_ip,
    storage_uri=LIMITER_REDIS_URL,
    strategy="fixed-window",
    headers_enabled=True,  # Return X-RateLimit-* headers to clients
)
