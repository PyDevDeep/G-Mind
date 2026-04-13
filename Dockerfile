# Stage 1: Builder — exports dependencies without dev packages
FROM python:3.11-slim AS builder

WORKDIR /app
# Використовуємо версію Poetry, сумісну з твоїм середовищем
ENV POETRY_VERSION=1.8.2 

RUN pip install --no-cache-dir "poetry==$POETRY_VERSION" poetry-plugin-export
COPY pyproject.toml poetry.lock* ./
RUN poetry export -f requirements.txt --output requirements.txt --without dev

# Stage 2: Final — lean runtime image
FROM python:3.11-slim

WORKDIR /app
# Забороняємо Python писати .pyc файли та буферизувати stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Встановлюємо curl для healthcheck    
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Створюємо non-root користувача для безпеки
RUN groupadd -r ai_email && useradd -r -g ai_email ai_email

# Встановлюємо залежності
COPY --from=builder /app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копіюємо вихідний код
COPY . .

# Передаємо права non-root користувачу
RUN chown -R ai_email:ai_email /app
USER ai_email