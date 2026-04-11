import os
import sys

# Додаємо корінь проєкту до шляху, щоб імпорти з src працювали
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.watch_service import WatchService
from src.utils.logging import configure_logging


def main():
    configure_logging(log_level="INFO")
    print("Ініціалізація Gmail Watch...")

    try:
        service = WatchService()
        result = service.setup_watch()
        print(f"\nУспішно! Поточний historyId: {result.get('historyId')}")
        print(f"Підписка діє до: {result.get('expiration')}")
    except Exception as e:
        print(f"\nПомилка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
