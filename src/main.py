import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

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
    """Мідлвара для трекінгу Correlation ID та логування запитів."""
    # Беремо ID з хедера або генеруємо новий
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    bind_correlation_id(correlation_id)

    logger.info("Incoming request", method=request.method, path=request.url.path)

    response = await call_next(request)

    logger.info("Request completed", status_code=response.status_code)
    response.headers["X-Correlation-ID"] = correlation_id

    return response


@app.get("/health")
async def health_check():
    """Liveness probe для Docker/Nginx."""
    return {"status": "ok"}
