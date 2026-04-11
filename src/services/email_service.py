import base64
import re
from email.mime.text import MIMEText
from typing import Any, Dict, List

from googleapiclient.errors import HttpError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from src.utils.gmail import GmailClient
from src.utils.logging import get_logger

logger = get_logger(__name__)


def is_retryable_http_error(exception: BaseException) -> bool:
    """Визначає, чи підлягає помилка HTTP повторному виконанню (429, 500+)."""
    if isinstance(exception, HttpError):
        if exception.resp.status in [429, 500, 502, 503, 504]:
            return True
    return False


class EmailService:
    def __init__(self):
        self.client = GmailClient()
        self.service = self.client.get_service()

    @retry(
        wait=wait_exponential(multiplier=1, min=4, max=60),
        stop=stop_after_attempt(5),
        retry=retry_if_exception(is_retryable_http_error),
        reraise=True,
    )
    def get_message(self, message_id: str, user_id: str = "me") -> Dict[str, Any]:
        """Отримує повний лист за ID з експоненційним бекофом при лімітах."""
        logger.info("Отримання листа", message_id=message_id)
        return (
            self.service.users()
            .messages()
            .get(userId=user_id, id=message_id, format="full")
            .execute()
        )

    def get_thread_messages(
        self, thread_id: str, limit: int = 5, user_id: str = "me"
    ) -> List[Dict[str, Any]]:
        """Отримує останні N повідомлень з гілки для контексту AI."""
        logger.info("Отримання гілки", thread_id=thread_id)
        thread = (
            self.service.users().threads().get(userId=user_id, id=thread_id).execute()
        )
        messages = thread.get("messages", [])
        return messages[-limit:]

    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        thread_id: str | None = None,
        user_id: str = "me",
    ) -> str:
        """Створює чернетку відповіді в Gmail."""
        logger.info("Створення чернетки", recipient=to, thread_id=thread_id)
        message = MIMEText(body)
        message["To"] = to
        message["Subject"] = subject

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        draft_body: Dict[str, Any] = {"message": {"raw": raw_message}}

        if thread_id:
            draft_body["message"]["threadId"] = thread_id

        draft = (
            self.service.users()
            .drafts()
            .create(userId=user_id, body=draft_body)
            .execute()
        )
        return draft["id"]

    def parse_email_body(self, payload: Dict[str, Any]) -> str:
        """Рекурсивно парсить multipart payload та витягує текст, очищаючи HTML."""

        def _strip_html(text: str) -> str:
            clean = re.compile("<.*?>")
            return re.sub(clean, "", text)

        def _extract_data(parts: List[Dict[str, Any]]) -> str:
            text_content = ""
            html_content = ""

            for part in parts:
                mime_type = part.get("mimeType")
                body = part.get("body", {})
                data = body.get("data")

                if mime_type == "text/plain" and data:
                    text_content += base64.urlsafe_b64decode(data).decode("utf-8")
                elif mime_type == "text/html" and data:
                    html_content += base64.urlsafe_b64decode(data).decode("utf-8")
                elif "parts" in part:
                    text_content += _extract_data(part["parts"])

            # Пріоритет: plain text. Якщо немає — беремо HTML і чистимо теги.
            if text_content:
                return text_content
            return _strip_html(html_content)

        if "parts" in payload:
            return _extract_data(payload["parts"])
        else:
            data = payload.get("body", {}).get("data")
            if data:
                raw_text = base64.urlsafe_b64decode(data).decode("utf-8")
                if payload.get("mimeType") == "text/html":
                    return _strip_html(raw_text)
                return raw_text
        return ""
