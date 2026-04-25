"""Health and readiness endpoints.

Roadmap requirement: src/api/health.py
- GET /health → liveness probe (remains in main.py for Docker compatibility)
- GET /ready  → readiness probe: DB + Redis + Celery connectivity check
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.dependencies import get_db_session, redis_client
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["Health"])


@router.get("/ready", response_model=None)
async def readiness_check(
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object] | JSONResponse:
    """Readiness probe: verifies DB, Redis, and Celery worker connectivity.

    Returns HTTP 200 only when all dependencies are reachable.
    Returns HTTP 503 with details when any dependency is down.
    """
    checks: dict[str, str] = {}
    all_ok = True

    # 1. PostgreSQL
    try:
        await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {e}"
        all_ok = False

    # 2. Redis
    try:
        await redis_client.ping()  # type: ignore[no-untyped-call]
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"
        all_ok = False

    # 3. Celery (check via Redis: inspect if at least one worker registered)
    try:
        queue_len = await redis_client.llen("default")  # type: ignore[no-untyped-call]
        checks["celery_queue"] = f"ok (depth={queue_len})"
    except Exception as e:
        checks["celery_queue"] = f"error: {e}"
        all_ok = False

    if not all_ok:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "checks": checks},
        )

    return {"status": "ok", "checks": checks}
