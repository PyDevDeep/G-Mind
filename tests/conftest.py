import os

import pytest


# Примусово перемикаємо Celery в синхронний режим для тестів,
# щоб .delay() виконувався миттєво в тому ж потоці.
@pytest.fixture(autouse=True)
def celery_eager():
    os.environ["CELERY_TASK_ALWAYS_EAGER"] = "True"
    os.environ["CELERY_TASK_EAGER_PROPAGATES"] = "True"
    from src.workers.celery_app import celery_app

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
