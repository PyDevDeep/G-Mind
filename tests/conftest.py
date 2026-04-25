import os

import pytest

# Must be set before any module imports so the code connects to Docker-forwarded ports on the host.
os.environ["REDIS_URL"] = "redis://localhost:6381/0"
os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://postgres:postgres_password@localhost:5434/ai_email_db"
)
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "True"
os.environ["CELERY_TASK_EAGER_PROPAGATES"] = "True"

from src.workers.celery_app import celery_app


@pytest.fixture(autouse=True)
def setup_celery():
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    return
