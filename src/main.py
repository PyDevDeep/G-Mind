import time
import uuid
from contextlib import asynccontextmanager
from typing import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from src.api.router import api_router
from src.config import get_settings
from src.dependencies import engine, redis_client
from src.utils.logging import bind_correlation_id, configure_logging, get_logger

settings = get_settings()

# Ініціалізація логування
# В production (VPS) краще встановити json_format=True
configure_logging(log_level=settings.LOG_LEVEL, json_format=False)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Керування життєвим циклом додатку (startup / shutdown)."""
    logger.info("Starting up API...")

    # Перевірка підключення до Redis
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


app.include_router(api_router)

# Безпека CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В production замінити на конкретні домени
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlation_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Покращена мідлвара з вимірюванням тривалості запиту."""
    start_time = time.perf_counter()

    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    bind_correlation_id(correlation_id)

    # Логуємо вхідний запит
    logger.info(
        "http_request_started",
        method=request.method,
        path=request.url.path,
        client_host=request.client.host if request.client else "unknown",
    )

    response = await call_next(request)

    process_time = time.perf_counter() - start_time

    # Логуємо завершення з тривалістю
    logger.info(
        "http_request_completed",
        status_code=response.status_code,
        duration=f"{process_time:.4f}s",
    )

    response.headers["X-Correlation-ID"] = correlation_id
    return response


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness probe для Docker/Nginx."""
    return {"status": "ok"}
