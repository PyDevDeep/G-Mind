import os

from fastapi import Request
from slowapi import Limiter


def get_real_ip(request: Request) -> str:
    """
    Витягує реальну IP-адресу клієнта, ігноруючи проксі-сервери.
    Якщо запит пройшов через кілька проксі, X-Forwarded-For міститиме список IP.
    Перший IP у списку - це оригінальний клієнт.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Фолбек для локальної розробки (коли немає проксі)
    return request.client.host if request.client else "127.0.0.1"


# Використовуємо Redis базу 1 для лімітів (Celery зазвичай використовує 0)
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
# Замінюємо базу на 1, якщо URL стандартний
LIMITER_REDIS_URL = REDIS_URL[:-1] + "1" if REDIS_URL.endswith("/0") else REDIS_URL

limiter = Limiter(
    key_func=get_real_ip,
    storage_uri=LIMITER_REDIS_URL,
    strategy="fixed-window",  # Класичне вікно (напр., 60 запитів з 00:00 до 00:01)
    headers_enabled=True,  # Повертає клієнту заголовки X-RateLimit-* (дуже важливо для API)
)
