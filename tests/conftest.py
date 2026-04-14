import os

import pytest

# КРИТИЧНО: Встановлюємо локальні порти для тестів ДО імпорту будь-яких модулів.
# Це змусить код стукатись у прокинуті порти Docker на хості.
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
    yield
