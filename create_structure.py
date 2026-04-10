import os

base = r"c:\AI\G_Mind - Copy"

dirs = [
    "alembic/versions",
    "src/api",
    "src/models",
    "src/schemas",
    "src/services",
    "src/workers",
    "src/utils",
    "tests/unit",
    "tests/integration",
    "tests/fixtures/emails",
    "tests/fixtures/responses",
    "monitoring/prometheus",
    "monitoring/grafana/dashboards",
    "monitoring/alertmanager",
    "scripts",
]

files = [
    "docker-compose.yml",
    "docker-compose.override.yml",
    "Dockerfile",
    ".env.example",
    ".gitignore",
    "pyproject.toml",
    "alembic.ini",
    "README.md",
    "alembic/env.py",
    "alembic/script.py.mako",
    "alembic/versions/001_initial_schema.py",
    "alembic/versions/002_add_failed_tasks.py",
    "src/__init__.py",
    "src/main.py",
    "src/config.py",
    "src/dependencies.py",
    "src/api/__init__.py",
    "src/api/router.py",
    "src/api/webhook.py",
    "src/api/health.py",
    "src/api/tasks.py",
    "src/models/__init__.py",
    "src/models/base.py",
    "src/models/email.py",
    "src/models/task.py",
    "src/models/response.py",
    "src/models/failed_task.py",
    "src/schemas/__init__.py",
    "src/schemas/webhook.py",
    "src/schemas/email.py",
    "src/schemas/task.py",
    "src/schemas/ai.py",
    "src/services/__init__.py",
    "src/services/email_service.py",
    "src/services/ai_service.py",
    "src/services/storage_service.py",
    "src/services/queue_service.py",
    "src/services/watch_service.py",
    "src/workers/__init__.py",
    "src/workers/celery_app.py",
    "src/workers/tasks.py",
    "src/workers/callbacks.py",
    "src/utils/__init__.py",
    "src/utils/logging.py",
    "src/utils/retry.py",
    "src/utils/pubsub.py",
    "src/utils/gmail.py",
    "tests/__init__.py",
    "tests/conftest.py",
    "tests/unit/test_email_service.py",
    "tests/unit/test_ai_service.py",
    "tests/unit/test_classification.py",
    "tests/unit/test_deduplication.py",
    "tests/integration/test_webhook_flow.py",
    "tests/integration/test_celery_tasks.py",
    "tests/integration/test_end_to_end.py",
    "monitoring/prometheus/prometheus.yml",
    "monitoring/grafana/dashboards/email-assistant.json",
    "monitoring/alertmanager/config.yml",
    "scripts/setup_watch.py",
    "scripts/seed_test_emails.py",
    "scripts/check_queue.py",
]

for d in dirs:
    path = os.path.join(base, d.replace("/", os.sep))
    os.makedirs(path, exist_ok=True)

for f in files:
    path = os.path.join(base, f.replace("/", os.sep))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        open(path, "w").close()

print("Done!")
