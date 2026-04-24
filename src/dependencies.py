from collections.abc import AsyncGenerator

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.config import get_settings

settings = get_settings()

# Global async database connection pool
engine = create_async_engine(
    settings.DATABASE_URL,
    poolclass=NullPool,
)
async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# Global Redis client
redis_client: Redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)  # type: ignore[no-untyped-call]


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session."""
    async with async_session_maker() as session:
        yield session


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency that yields the shared Redis client."""
    yield redis_client
