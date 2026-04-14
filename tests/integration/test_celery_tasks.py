"""
Integration tests for Celery tasks: classify_email, generate_ai_reply, send_draft.

Coverage:
- classify_email: needs_reply → chains generate_ai_reply
- classify_email: non-needs_reply → НЕ chains generate_ai_reply
- classify_email: LLMRateLimitError → прокидається (ретрай логіка Celery)
- generate_ai_reply: успіх → chains send_draft
- send_draft: успіх → повертає draft_id
- handle_task_failure callback: без email_id в args → логується, не падає

Примітка: task_always_eager=True вже виставлено в conftest.py.
WorkerService мокується повністю щоб уникнути конфлікту asyncio.run() з pytest event loop.
"""

from typing import cast as _cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from celery import Task

from src.workers.tasks import (
    LLMRateLimitError,
    classify_email,
    generate_ai_reply,
    send_draft,
)

# Pylance не бачить .apply() на Celery-декорованих функціях — cast прибирає false-positive
_classify = _cast(Task, classify_email)
_generate = _cast(Task, generate_ai_reply)
_send = _cast(Task, send_draft)


# ---------------------------------------------------------------------------
# classify_email
# ---------------------------------------------------------------------------


class TestClassifyEmailTask:
    def test_classify_needs_reply_chains_generate_ai_reply(self) -> None:
        """Якщо classify повертає needs_reply — автоматично ставиться generate_ai_reply."""
        with patch("src.workers.tasks.WorkerService") as MockWorker:
            instance = MockWorker.return_value
            instance.process_classification = AsyncMock(
                return_value={"category": "needs_reply", "task_id": "task-1"}
            )

            with patch("src.workers.tasks.generate_ai_reply") as mock_chain:
                mock_chain.delay = MagicMock()
                _classify.apply(args=["email-1"])

            mock_chain.delay.assert_called_once_with("email-1", None)

    def test_classify_non_needs_reply_does_not_chain(self) -> None:
        """Якщо категорія не needs_reply — generate_ai_reply НЕ викликається."""
        with patch("src.workers.tasks.WorkerService") as MockWorker:
            instance = MockWorker.return_value
            instance.process_classification = AsyncMock(
                return_value={"category": "spam", "task_id": "task-2"}
            )

            with patch("src.workers.tasks.generate_ai_reply") as mock_chain:
                mock_chain.delay = MagicMock()
                _classify.apply(args=["email-2"])

            mock_chain.delay.assert_not_called()

    def test_classify_llm_rate_limit_raises(self) -> None:
        """LLMRateLimitError → Celery eager mode піднімає Retry (autoretry_for механізм)."""
        from celery.exceptions import Retry

        with patch("src.workers.tasks.WorkerService") as MockWorker:
            instance = MockWorker.return_value
            instance.process_classification = AsyncMock(
                side_effect=LLMRateLimitError("rate limit")
            )

            # eager mode: autoretry_for перетворює LLMRateLimitError на Retry exception
            with pytest.raises(Retry):
                _classify.apply(args=["email-3"])

    def test_classify_returns_status_and_email_id(self) -> None:
        """Повертає dict із status та email_id."""
        with patch("src.workers.tasks.WorkerService") as MockWorker:
            instance = MockWorker.return_value
            instance.process_classification = AsyncMock(
                return_value={"category": "informational", "task_id": "task-3"}
            )

            with patch("src.workers.tasks.generate_ai_reply") as mock_chain:
                mock_chain.delay = MagicMock()
                result: dict[str, str] = _classify.apply(args=["email-4"]).get()  # type: ignore[assignment]

        assert result["status"] == "classified"
        assert result["email_id"] == "email-4"


# ---------------------------------------------------------------------------
# generate_ai_reply
# ---------------------------------------------------------------------------


class TestGenerateAiReplyTask:
    def test_success_chains_send_draft(self) -> None:
        """Успішна генерація → ставить send_draft в чергу."""
        with patch("src.workers.tasks.WorkerService") as MockWorker:
            instance = MockWorker.return_value
            instance.process_reply_generation = AsyncMock(
                return_value={"task_id": "task-1"}
            )

            with patch("src.workers.tasks.send_draft") as mock_send:
                mock_send.delay = MagicMock()
                _generate.apply(args=["email-1"])

            mock_send.delay.assert_called_once_with("email-1", None)

    def test_exception_propagates(self) -> None:
        """Помилка WorkerService прокидається назовні."""
        with patch("src.workers.tasks.WorkerService") as MockWorker:
            instance = MockWorker.return_value
            instance.process_reply_generation = AsyncMock(
                side_effect=ValueError("no ai response")
            )

            with pytest.raises(ValueError, match="no ai response"):
                _generate.apply(args=["email-1"])


# ---------------------------------------------------------------------------
# send_draft
# ---------------------------------------------------------------------------


class TestSendDraftTask:
    def test_success_returns_draft_id(self) -> None:
        """Успішне виконання повертає draft_id в результаті."""
        with patch("src.workers.tasks.WorkerService") as MockWorker:
            instance = MockWorker.return_value
            instance.process_send_draft = AsyncMock(
                return_value={"draft_id": "draft-xyz"}
            )

            result: dict[str, str] = _send.apply(args=["email-1"]).get()  # type: ignore[assignment]

        assert result["status"] == "draft_created"
        assert result["draft_id"] == "draft-xyz"

    def test_exception_propagates(self) -> None:
        """Помилка WorkerService прокидається назовні."""
        with patch("src.workers.tasks.WorkerService") as MockWorker:
            instance = MockWorker.return_value
            instance.process_send_draft = AsyncMock(
                side_effect=ValueError("no reply data")
            )

            with pytest.raises(ValueError, match="no reply data"):
                _send.apply(args=["email-1"])


# ---------------------------------------------------------------------------
# handle_task_failure callback — edge case: відсутній email_id
# ---------------------------------------------------------------------------


class TestHandleTaskFailureCallback:
    def test_no_email_id_in_args_does_not_raise(self) -> None:
        """Якщо args порожній — callback логує помилку і повертається без виключення."""
        from src.workers.callbacks import handle_task_failure

        mock_sender = MagicMock()
        mock_sender.name = "src.workers.tasks.classify_email"

        # Не має кидати виняток
        handle_task_failure(
            sender=mock_sender,
            task_id="celery-id-1",
            exception=RuntimeError("boom"),
            args=(),  # порожній args
            kwargs={},
            einfo=None,
        )

    def test_no_email_id_in_kwargs_does_not_raise(self) -> None:
        """Якщо kwargs без email_id — callback повертається без виключення."""
        from src.workers.callbacks import handle_task_failure

        mock_sender = MagicMock()
        mock_sender.name = "src.workers.tasks.classify_email"

        handle_task_failure(
            sender=mock_sender,
            task_id="celery-id-2",
            exception=ValueError("err"),
            args=None,
            kwargs={"some_other_key": "value"},
            einfo=None,
        )

    def test_none_exception_handled_gracefully(self) -> None:
        """exception=None замінюється на Exception('Unknown error') — не падає."""
        from src.workers.callbacks import handle_task_failure

        mock_sender = MagicMock()
        mock_sender.name = "some.task"

        # Не має кидати AttributeError або TypeError
        handle_task_failure(
            sender=mock_sender,
            task_id="celery-id-3",
            exception=None,
            args=("email-orphan",),
            kwargs={},
            einfo=None,
        )
