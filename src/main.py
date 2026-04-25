"""FastAPI application factory.

Changes vs original:
- Security headers (HSTS, X-Frame-Options, X-Content-Type-Options, CSP,
  Referrer-Policy, Permissions-Policy) injected via existing HTTP middleware
- Avoids adding a second middleware — headers set in correlation_id_middleware
"""

import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from src.api.router import api_router
from src.config import get_settings
from src.dependencies import engine, redis_client
from src.utils.limiter import limiter
from src.utils.logging import bind_correlation_id, configure_logging, get_logger

settings = get_settings()

# Initialize logging (set json_format=True in production / VPS)
configure_logging(log_level=settings.LOG_LEVEL, json_format=False)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle."""
    logger.info("Starting up API...")

    # Verify Redis connectivity on startup
    try:
        await redis_client.ping()  # type: ignore[no-untyped-call]
        logger.info("Redis connection established.")
    except Exception as e:
        logger.error("Redis connection failed", error=str(e))

    yield

    logger.info("Shutting down API...")
    await engine.dispose()
    await redis_client.close()


app = FastAPI(title="AI Email Assistant", lifespan=lifespan)
# Required by slowapi: attach limiter to app state
app.state.limiter = limiter
# Return proper JSON on rate-limit instead of Internal Server Error
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
# Instrument and expose standard FastAPI Prometheus metrics
Instrumentator().instrument(app).expose(app)
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    # Restrict to methods actually used by this API
    allow_methods=["GET", "POST", "OPTIONS"],
    # Restrict to headers expected by this API
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


# ---------------------------------------------------------------------------
# Security headers (roadmap: TASK 5.1.2)
# ---------------------------------------------------------------------------
_SECURITY_HEADERS: dict[str, str] = {
    # Prevent clickjacking — this API has no pages to frame
    "X-Frame-Options": "DENY",
    # Stop browsers from MIME-sniffing the content-type
    "X-Content-Type-Options": "nosniff",
    # Enable HSTS — force HTTPS for 1 year, including subdomains
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    # Restrict resources to same-origin; allow inline styles for Swagger UI
    "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:",
    # Send origin only on cross-origin requests
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # Disable browser features this API doesn't need
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


@app.middleware("http")
async def correlation_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Propagate correlation ID, log request duration, and inject security headers."""
    start_time = time.perf_counter()

    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    bind_correlation_id(correlation_id)

    logger.info(
        "http_request_started",
        method=request.method,
        path=request.url.path,
        client_host=request.client.host if request.client else "unknown",
    )

    response = await call_next(request)

    process_time = time.perf_counter() - start_time

    logger.info(
        "http_request_completed",
        status_code=response.status_code,
        duration=f"{process_time:.4f}s",
    )

    response.headers["X-Correlation-ID"] = correlation_id

    # Inject security headers into every response
    for header, value in _SECURITY_HEADERS.items():
        response.headers[header] = value

    return response


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness probe for Docker/Nginx."""
    return {"status": "ok"}
