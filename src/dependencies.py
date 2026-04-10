from typing import AsyncGenerator

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import get_settings

settings = get_settings()

# Глобальний пул підключень до бази даних
engine = create_async_engine(
    settings.DATABASE_URL, pool_size=20, max_overflow=10, pool_pre_ping=True
)
async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# Глобальний клієнт Redis
redis_client: Redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)  # type: ignore[no-untyped-call]


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency для ін'єкції сесії БД у роути FastAPI."""
    async with async_session_maker() as session:
        yield session


async def get_redis() -> AsyncGenerator[Redis, None]:
    """Dependency для ін'єкції Redis."""
    yield redis_client
