import os.path
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Скоупи, необхідні для нашого AI Assistant
# readonly для читання листів, compose для створення драфтів (без прямого надсилання)
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]


def main():
    """Виконує OAuth 2.0 flow та зберігає токени у token.json"""
    creds = None

    # Шляхи до файлів (враховуючи, що скрипт запускається з кореня)
    creds_path = "credentials.json"
    token_path = "token.json"

    if not os.path.exists(creds_path):
        print(f"Помилка: Файл {creds_path} не знайдено!")
        print("Завантаж його з Google Cloud Console та поклади в корінь проєкту.")
        sys.exit(1)

    # Завантаження існуючого токена, якщо він є
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    # Якщо немає валідних credentials, робимо логін
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Оновлення існуючого токена...")
            creds.refresh(Request())
        else:
            print("Запуск OAuth flow...")
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            # Запускає локальний сервер на порту 8080 для колбеку від Google
            creds = flow.run_local_server(port=8080)

        # Збереження токена для наступних запусків
        with open(token_path, "w") as token:
            token.write(creds.to_json())
            print(f"Успіх! Токени збережено у {token_path}")


if __name__ == "__main__":
    main()
