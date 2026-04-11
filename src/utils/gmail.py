import os
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build  # type: ignore[import-untyped]

from src.utils.logging import get_logger

logger = get_logger(__name__)


class GmailClient:
    def __init__(self, token_path: str = "token.json"):
        self.token_path = token_path
        self.scopes = [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.compose",
        ]

    def get_service(self) -> Any:
        """Отримує автентифікований сервіс Gmail API, оновлює токен за потреби."""
        creds = None
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, self.scopes)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Оновлення простроченого Gmail токена")
                creds.refresh(Request())
                with open(self.token_path, "w") as token:
                    token.write(creds.to_json())
            else:
                logger.error("Відсутні валідні credentials. Виконай oauth_flow.py.")
                raise RuntimeError("Gmail authentication failed. Missing valid token.")

        return build("gmail", "v1", credentials=creds, cache_discovery=False)  # type: ignore[no-any-return]
