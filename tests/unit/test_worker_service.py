"""
Tests for WorkerService: unit coverage of all async methods.

Coverage:
- process_classification: entity not found raises ValueError
- process_classification: missing email (task exists) raises ValueError
- process_classification: invalid UUID string raises ValueError
- process_classification: happy path returns category + task_id
- process_classification: verifies task status transitions (processing → classified)
- process_reply_generation: email/task not found raises ValueError
- process_reply_generation: no ai_response record raises ValueError
- process_reply_generation: happy path returns task_id
- process_send_draft: email/task not found raises ValueError
- process_send_draft: ai_response missing raises ValueError
- process_send_draft: generated_reply=None raises ValueError
- process_send_draft: corrupted JSON in generated_reply raises JSONDecodeError
- process_send_draft: happy path returns draft_id and commits session
- process_task_failure: records error and sets failed status; commits session
- process_task_failure: skips gracefully if task not found (no commit)
- process_task_failure: preserves exception type in error_type field

Strategy: mock async_session_maker context manager + StorageService methods.
WorkerService.ai_service замокується через patch at fixture level.
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.models.task import TaskStatusEnum
from src.schemas.ai import AIUsageStats, ClassificationCategory, ClassificationResult
from src.services.worker_service import WorkerService

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_email(
    email_id: uuid.UUID | None = None,
    thread_id: str = "thr-1",
    body: str = "test body",
    sender: str = "a@b.com",
) -> MagicMock:
    e = MagicMock()
    e.id = email_id or uuid.uuid4()
    e.thread_id = thread_id
    e.body = body
    e.subject = "Subject"
    e.sender = sender
    return e


def _make_task(task_id: uuid.UUID | None = None) -> MagicMock:
    t = MagicMock()
    t.id = task_id or uuid.uuid4()
    return t


def _make_ai_response(
    classification: str = "needs_reply",
    generated_reply: str | None = '{"subject":"Re","body":"Hi","tone":"pro"}',
    confidence_score: float = 0.9,
) -> MagicMock:
    r = MagicMock()
    r.classification = classification
    r.confidence_score = confidence_score
    r.generated_reply = generated_reply
    return r


def _make_classification_result(
    category: ClassificationCategory = ClassificationCategory.informational,
    confidence: float = 0.8,
) -> ClassificationResult:
    return ClassificationResult(
        category=category,
        confidence_score=confidence,
        reasoning="test reasoning",
    )


def _make_ai_stats() -> AIUsageStats:
    return AIUsageStats(model_used="gpt-4o", prompt_tokens=10, completion_tokens=5)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def worker() -> WorkerService:
    """WorkerService з замокованим AIService (без реального __init__)."""
    with patch("src.services.worker_service.AIService.__init__", return_value=None):
        svc = WorkerService()
        svc.ai_service = MagicMock()
        return svc


@pytest.fixture
def mock_session_ctx() -> tuple[MagicMock, AsyncMock]:
    """
    Контекстний менеджер для async_session_maker.
    Повертає (mock_maker, mock_session) — session можна конфігурувати в тесті.
    """
    mock_session = AsyncMock()
    mock_maker = MagicMock()
    mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_maker, mock_session


# ---------------------------------------------------------------------------
# process_classification
# ---------------------------------------------------------------------------


class TestProcessClassification:
    async def test_raises_value_error_when_email_not_found(
        self, worker: WorkerService, mock_session_ctx: tuple[MagicMock, AsyncMock]
    ) -> None:
        """Якщо email не знайдено — ValueError з повідомленням про entity."""
        mock_maker, _ = mock_session_ctx
        email_id = str(uuid.uuid4())

        with patch("src.services.worker_service.async_session_maker", mock_maker):
            with patch("src.services.worker_service.StorageService") as MockStorage:
                storage_inst = AsyncMock()
                storage_inst.get_email = AsyncMock(return_value=None)
                storage_inst.get_task_by_email_id = AsyncMock(return_value=None)
                MockStorage.return_value = storage_inst

                with pytest.raises(ValueError, match="Entity not found"):
                    await worker.process_classification(email_id)

    async def test_raises_value_error_when_task_not_found(
        self, worker: WorkerService, mock_session_ctx: tuple[MagicMock, AsyncMock]
    ) -> None:
        """Якщо task не знайдено — ValueError навіть якщо email є."""
        mock_maker, _ = mock_session_ctx
        email_id = str(uuid.uuid4())

        with patch("src.services.worker_service.async_session_maker", mock_maker):
            with patch("src.services.worker_service.StorageService") as MockStorage:
                storage_inst = AsyncMock()
                storage_inst.get_email = AsyncMock(return_value=_make_email())
                storage_inst.get_task_by_email_id = AsyncMock(return_value=None)
                MockStorage.return_value = storage_inst

                with pytest.raises(ValueError, match="Entity not found"):
                    await worker.process_classification(email_id)

    async def test_raises_value_error_on_invalid_uuid_string(
        self, worker: WorkerService
    ) -> None:
        """Невалідний UUID-рядок має підняти ValueError ще до звернення до storage."""
        with pytest.raises(ValueError):
            await worker.process_classification("not-a-uuid")

    async def test_returns_category_on_success(
        self, worker: WorkerService, mock_session_ctx: tuple[MagicMock, AsyncMock]
    ) -> None:
        """Happy path: повертає category та task_id."""
        mock_maker, _ = mock_session_ctx
        email_id = str(uuid.uuid4())
        task_id = uuid.uuid4()
        fake_email = _make_email()
        fake_task = _make_task(task_id)
        fake_classification = _make_classification_result(
            ClassificationCategory.informational
        )
        fake_stats = _make_ai_stats()

        with patch("src.services.worker_service.async_session_maker", mock_maker):
            with patch("src.services.worker_service.StorageService") as MockStorage:
                storage_inst = AsyncMock()
                storage_inst.get_email = AsyncMock(return_value=fake_email)
                storage_inst.get_task_by_email_id = AsyncMock(return_value=fake_task)
                storage_inst.update_task_status = AsyncMock()
                storage_inst.upsert_ai_response = AsyncMock()
                MockStorage.return_value = storage_inst

                with patch(
                    "src.services.worker_service.asyncio.to_thread",
                    new=AsyncMock(return_value=(fake_classification, fake_stats)),
                ):
                    result = await worker.process_classification(email_id)

        assert result["category"] == "informational"
        assert result["task_id"] == str(task_id)

    async def test_task_status_transitions_processing_then_classified(
        self, worker: WorkerService, mock_session_ctx: tuple[MagicMock, AsyncMock]
    ) -> None:
        """Після успішної класифікації статус проходить processing → classified."""
        mock_maker, _ = mock_session_ctx
        email_id = str(uuid.uuid4())
        task_id = uuid.uuid4()
        fake_task = _make_task(task_id)

        with patch("src.services.worker_service.async_session_maker", mock_maker):
            with patch("src.services.worker_service.StorageService") as MockStorage:
                storage_inst = AsyncMock()
                storage_inst.get_email = AsyncMock(return_value=_make_email())
                storage_inst.get_task_by_email_id = AsyncMock(return_value=fake_task)
                storage_inst.update_task_status = AsyncMock()
                storage_inst.upsert_ai_response = AsyncMock()
                MockStorage.return_value = storage_inst

                with patch(
                    "src.services.worker_service.asyncio.to_thread",
                    new=AsyncMock(
                        return_value=(
                            _make_classification_result(ClassificationCategory.spam),
                            _make_ai_stats(),
                        )
                    ),
                ):
                    await worker.process_classification(email_id)

        assert storage_inst.update_task_status.await_count == 2
        calls = storage_inst.update_task_status.await_args_list
        assert calls[0] == call(task_id, TaskStatusEnum.processing)
        assert calls[1] == call(task_id, TaskStatusEnum.classified)

    async def test_upsert_ai_response_called_with_correct_args(
        self, worker: WorkerService, mock_session_ctx: tuple[MagicMock, AsyncMock]
    ) -> None:
        """upsert_ai_response отримує правильні аргументи після класифікації."""
        mock_maker, _ = mock_session_ctx
        email_id = str(uuid.uuid4())
        task_id = uuid.uuid4()
        fake_task = _make_task(task_id)
        fake_stats = AIUsageStats(
            model_used="gpt-4o", prompt_tokens=20, completion_tokens=10
        )
        fake_cls = _make_classification_result(
            ClassificationCategory.urgent, confidence=0.95
        )

        with patch("src.services.worker_service.async_session_maker", mock_maker):
            with patch("src.services.worker_service.StorageService") as MockStorage:
                storage_inst = AsyncMock()
                storage_inst.get_email = AsyncMock(return_value=_make_email())
                storage_inst.get_task_by_email_id = AsyncMock(return_value=fake_task)
                storage_inst.update_task_status = AsyncMock()
                storage_inst.upsert_ai_response = AsyncMock()
                MockStorage.return_value = storage_inst

                with patch(
                    "src.services.worker_service.asyncio.to_thread",
                    new=AsyncMock(return_value=(fake_cls, fake_stats)),
                ):
                    await worker.process_classification(email_id)

        storage_inst.upsert_ai_response.assert_awaited_once_with(
            task_id=task_id,
            classification="urgent",
            confidence=0.95,
            stats=fake_stats,
        )


# ---------------------------------------------------------------------------
# process_reply_generation
# ---------------------------------------------------------------------------


class TestProcessReplyGeneration:
    async def test_raises_value_error_when_entities_missing(
        self, worker: WorkerService, mock_session_ctx: tuple[MagicMock, AsyncMock]
    ) -> None:
        """Якщо email і task не знайдено — ValueError 'Not found'."""
        mock_maker, _ = mock_session_ctx
        email_id = str(uuid.uuid4())

        with patch("src.services.worker_service.async_session_maker", mock_maker):
            with patch("src.services.worker_service.StorageService") as MockStorage:
                storage_inst = AsyncMock()
                storage_inst.get_email = AsyncMock(return_value=None)
                storage_inst.get_task_by_email_id = AsyncMock(return_value=None)
                MockStorage.return_value = storage_inst

                with pytest.raises(ValueError, match="Not found"):
                    await worker.process_reply_generation(email_id)

    async def test_raises_value_error_when_only_task_missing(
        self, worker: WorkerService, mock_session_ctx: tuple[MagicMock, AsyncMock]
    ) -> None:
        """Якщо email є, але task відсутній — ValueError."""
        mock_maker, _ = mock_session_ctx
        email_id = str(uuid.uuid4())

        with patch("src.services.worker_service.async_session_maker", mock_maker):
            with patch("src.services.worker_service.StorageService") as MockStorage:
                storage_inst = AsyncMock()
                storage_inst.get_email = AsyncMock(return_value=_make_email())
                storage_inst.get_task_by_email_id = AsyncMock(return_value=None)
                MockStorage.return_value = storage_inst

                with pytest.raises(ValueError, match="Not found"):
                    await worker.process_reply_generation(email_id)

    async def test_raises_value_error_when_ai_response_missing(
        self, worker: WorkerService, mock_session_ctx: tuple[MagicMock, AsyncMock]
    ) -> None:
        """Якщо AIResponse не існує — ValueError 'AI Response not found'."""
        mock_maker, _ = mock_session_ctx
        email_id = str(uuid.uuid4())

        with patch("src.services.worker_service.async_session_maker", mock_maker):
            with patch("src.services.worker_service.StorageService") as MockStorage:
                storage_inst = AsyncMock()
                storage_inst.get_email = AsyncMock(return_value=_make_email())
                storage_inst.get_task_by_email_id = AsyncMock(return_value=_make_task())
                storage_inst.get_ai_response_by_task_id = AsyncMock(return_value=None)
                MockStorage.return_value = storage_inst

                with patch(
                    "src.services.worker_service.asyncio.to_thread",
                    new=AsyncMock(return_value=[]),
                ):
                    with pytest.raises(ValueError, match="AI Response not found"):
                        await worker.process_reply_generation(email_id)

    async def test_raises_value_error_on_invalid_uuid(
        self, worker: WorkerService
    ) -> None:
        """Невалідний UUID піднімає ValueError до звернення до storage."""
        with pytest.raises(ValueError):
            await worker.process_reply_generation("bad-uuid-string")

    async def test_returns_task_id_on_success(
        self, worker: WorkerService, mock_session_ctx: tuple[MagicMock, AsyncMock]
    ) -> None:
        """Happy path: повертає task_id після генерації відповіді."""
        from src.schemas.ai import GeneratedReply

        mock_maker, _ = mock_session_ctx
        email_id = str(uuid.uuid4())
        task_id = uuid.uuid4()
        fake_reply = GeneratedReply(
            subject="Re: test", body="Hello", tone="professional"
        )
        fake_stats = _make_ai_stats()

        with patch("src.services.worker_service.async_session_maker", mock_maker):
            with patch("src.services.worker_service.StorageService") as MockStorage:
                storage_inst = AsyncMock()
                storage_inst.get_email = AsyncMock(return_value=_make_email())
                storage_inst.get_task_by_email_id = AsyncMock(
                    return_value=_make_task(task_id)
                )
                storage_inst.get_ai_response_by_task_id = AsyncMock(
                    return_value=_make_ai_response()
                )
                storage_inst.upsert_ai_response = AsyncMock()
                storage_inst.update_task_status = AsyncMock()
                MockStorage.return_value = storage_inst

                # to_thread викликається двічі: get_thread_messages + generate_reply
                to_thread_mock = AsyncMock(side_effect=[[], (fake_reply, fake_stats)])
                with patch(
                    "src.services.worker_service.asyncio.to_thread", new=to_thread_mock
                ):
                    with patch("src.services.worker_service.EmailService"):
                        result = await worker.process_reply_generation(email_id)

        assert result["task_id"] == str(task_id)

    async def test_status_set_to_generating_reply_on_success(
        self, worker: WorkerService, mock_session_ctx: tuple[MagicMock, AsyncMock]
    ) -> None:
        """Після успішної генерації статус task → generating_reply."""
        from src.schemas.ai import GeneratedReply

        mock_maker, _ = mock_session_ctx
        email_id = str(uuid.uuid4())
        task_id = uuid.uuid4()
        fake_reply = GeneratedReply(subject="Re", body="body", tone="pro")
        fake_stats = _make_ai_stats()

        with patch("src.services.worker_service.async_session_maker", mock_maker):
            with patch("src.services.worker_service.StorageService") as MockStorage:
                storage_inst = AsyncMock()
                storage_inst.get_email = AsyncMock(return_value=_make_email())
                storage_inst.get_task_by_email_id = AsyncMock(
                    return_value=_make_task(task_id)
                )
                storage_inst.get_ai_response_by_task_id = AsyncMock(
                    return_value=_make_ai_response()
                )
                storage_inst.upsert_ai_response = AsyncMock()
                storage_inst.update_task_status = AsyncMock()
                MockStorage.return_value = storage_inst

                to_thread_mock = AsyncMock(side_effect=[[], (fake_reply, fake_stats)])
                with patch(
                    "src.services.worker_service.asyncio.to_thread", new=to_thread_mock
                ):
                    with patch("src.services.worker_service.EmailService"):
                        await worker.process_reply_generation(email_id)

        storage_inst.update_task_status.assert_awaited_once_with(
            task_id, TaskStatusEnum.generating_reply
        )


# ---------------------------------------------------------------------------
# process_send_draft
# ---------------------------------------------------------------------------


class TestProcessSendDraft:
    async def test_raises_value_error_when_entities_missing(
        self, worker: WorkerService, mock_session_ctx: tuple[MagicMock, AsyncMock]
    ) -> None:
        """Email і task відсутні — ValueError 'Not found'."""
        mock_maker, _ = mock_session_ctx
        email_id = str(uuid.uuid4())

        with patch("src.services.worker_service.async_session_maker", mock_maker):
            with patch("src.services.worker_service.StorageService") as MockStorage:
                storage_inst = AsyncMock()
                storage_inst.get_email = AsyncMock(return_value=None)
                storage_inst.get_task_by_email_id = AsyncMock(return_value=None)
                MockStorage.return_value = storage_inst

                with pytest.raises(ValueError, match="Not found"):
                    await worker.process_send_draft(email_id)

    async def test_raises_value_error_when_ai_response_missing(
        self, worker: WorkerService, mock_session_ctx: tuple[MagicMock, AsyncMock]
    ) -> None:
        """AIResponse відсутній — ValueError 'No reply data'."""
        mock_maker, _ = mock_session_ctx
        email_id = str(uuid.uuid4())

        with patch("src.services.worker_service.async_session_maker", mock_maker):
            with patch("src.services.worker_service.StorageService") as MockStorage:
                storage_inst = AsyncMock()
                storage_inst.get_email = AsyncMock(return_value=_make_email())
                storage_inst.get_task_by_email_id = AsyncMock(return_value=_make_task())
                storage_inst.get_ai_response_by_task_id = AsyncMock(return_value=None)
                MockStorage.return_value = storage_inst

                with pytest.raises(ValueError, match="No reply data"):
                    await worker.process_send_draft(email_id)

    async def test_raises_value_error_when_no_generated_reply(
        self, worker: WorkerService, mock_session_ctx: tuple[MagicMock, AsyncMock]
    ) -> None:
        """AIResponse існує але generated_reply=None — ValueError 'No reply data'."""
        mock_maker, _ = mock_session_ctx
        email_id = str(uuid.uuid4())

        with patch("src.services.worker_service.async_session_maker", mock_maker):
            with patch("src.services.worker_service.StorageService") as MockStorage:
                storage_inst = AsyncMock()
                storage_inst.get_email = AsyncMock(return_value=_make_email())
                storage_inst.get_task_by_email_id = AsyncMock(return_value=_make_task())
                storage_inst.get_ai_response_by_task_id = AsyncMock(
                    return_value=_make_ai_response(generated_reply=None)
                )
                MockStorage.return_value = storage_inst

                with pytest.raises(ValueError, match="No reply data"):
                    await worker.process_send_draft(email_id)

    async def test_raises_json_decode_error_on_corrupt_reply(
        self, worker: WorkerService, mock_session_ctx: tuple[MagicMock, AsyncMock]
    ) -> None:
        """Corrupt JSON у generated_reply → JSONDecodeError без поглинання."""
        mock_maker, _ = mock_session_ctx
        email_id = str(uuid.uuid4())

        with patch("src.services.worker_service.async_session_maker", mock_maker):
            with patch("src.services.worker_service.StorageService") as MockStorage:
                storage_inst = AsyncMock()
                storage_inst.get_email = AsyncMock(return_value=_make_email())
                storage_inst.get_task_by_email_id = AsyncMock(return_value=_make_task())
                storage_inst.get_ai_response_by_task_id = AsyncMock(
                    return_value=_make_ai_response(generated_reply="{invalid json}")
                )
                MockStorage.return_value = storage_inst

                with pytest.raises(json.JSONDecodeError):
                    await worker.process_send_draft(email_id)

    async def test_returns_draft_id_on_success(
        self, worker: WorkerService, mock_session_ctx: tuple[MagicMock, AsyncMock]
    ) -> None:
        """Happy path: повертає draft_id після успішного create_draft."""
        mock_maker, _ = mock_session_ctx
        email_id = str(uuid.uuid4())

        with patch("src.services.worker_service.async_session_maker", mock_maker):
            with patch("src.services.worker_service.StorageService") as MockStorage:
                storage_inst = AsyncMock()
                storage_inst.get_email = AsyncMock(return_value=_make_email())
                storage_inst.get_task_by_email_id = AsyncMock(return_value=_make_task())
                storage_inst.get_ai_response_by_task_id = AsyncMock(
                    return_value=_make_ai_response()
                )
                storage_inst.update_task_completed = AsyncMock()
                MockStorage.return_value = storage_inst

                with patch(
                    "src.services.worker_service.asyncio.to_thread",
                    new=AsyncMock(return_value="draft-999"),
                ):
                    with patch("src.services.worker_service.EmailService"):
                        result = await worker.process_send_draft(email_id)

        assert result["draft_id"] == "draft-999"

    async def test_update_task_completed_called_with_draft_id(
        self, worker: WorkerService, mock_session_ctx: tuple[MagicMock, AsyncMock]
    ) -> None:
        """update_task_completed отримує правильний task_id і draft_id."""
        mock_maker, _ = mock_session_ctx
        email_id = str(uuid.uuid4())
        task_id = uuid.uuid4()
        fake_task = _make_task(task_id)

        with patch("src.services.worker_service.async_session_maker", mock_maker):
            with patch("src.services.worker_service.StorageService") as MockStorage:
                storage_inst = AsyncMock()
                storage_inst.get_email = AsyncMock(return_value=_make_email())
                storage_inst.get_task_by_email_id = AsyncMock(return_value=fake_task)
                storage_inst.get_ai_response_by_task_id = AsyncMock(
                    return_value=_make_ai_response()
                )
                storage_inst.update_task_completed = AsyncMock()
                MockStorage.return_value = storage_inst

                with patch(
                    "src.services.worker_service.asyncio.to_thread",
                    new=AsyncMock(return_value="draft-42"),
                ):
                    with patch("src.services.worker_service.EmailService"):
                        await worker.process_send_draft(email_id)

        storage_inst.update_task_completed.assert_awaited_once_with(task_id, "draft-42")

    async def test_session_commit_called_on_success(
        self, worker: WorkerService, mock_session_ctx: tuple[MagicMock, AsyncMock]
    ) -> None:
        """session.commit() має бути викликано після успішного збереження чернетки."""
        mock_maker, mock_session = mock_session_ctx
        email_id = str(uuid.uuid4())

        with patch("src.services.worker_service.async_session_maker", mock_maker):
            with patch("src.services.worker_service.StorageService") as MockStorage:
                storage_inst = AsyncMock()
                storage_inst.get_email = AsyncMock(return_value=_make_email())
                storage_inst.get_task_by_email_id = AsyncMock(return_value=_make_task())
                storage_inst.get_ai_response_by_task_id = AsyncMock(
                    return_value=_make_ai_response()
                )
                storage_inst.update_task_completed = AsyncMock()
                MockStorage.return_value = storage_inst

                with patch(
                    "src.services.worker_service.asyncio.to_thread",
                    new=AsyncMock(return_value="draft-1"),
                ):
                    with patch("src.services.worker_service.EmailService"):
                        await worker.process_send_draft(email_id)

        mock_session.commit.assert_awaited_once()

    @pytest.mark.parametrize(
        "reply_json,expected_subject,expected_body",
        [
            (
                '{"subject":"Re: Hello","body":"Thanks","tone":"pro"}',
                "Re: Hello",
                "Thanks",
            ),
            (
                '{"tone":"pro"}',
                "Re:",
                "",
            ),  # відсутні ключі → дефолтні значення з .get()
        ],
    )
    async def test_reply_data_parsed_with_defaults(
        self,
        worker: WorkerService,
        mock_session_ctx: tuple[MagicMock, AsyncMock],
        reply_json: str,
        expected_subject: str,
        expected_body: str,
    ) -> None:
        """create_draft отримує правильні subject/body з JSON або дефолти через .get()."""
        mock_maker, _ = mock_session_ctx
        email_id = str(uuid.uuid4())
        fake_email = _make_email(sender="recipient@example.com", thread_id="thr-42")

        with patch("src.services.worker_service.async_session_maker", mock_maker):
            with patch("src.services.worker_service.StorageService") as MockStorage:
                storage_inst = AsyncMock()
                storage_inst.get_email = AsyncMock(return_value=fake_email)
                storage_inst.get_task_by_email_id = AsyncMock(return_value=_make_task())
                storage_inst.get_ai_response_by_task_id = AsyncMock(
                    return_value=_make_ai_response(generated_reply=reply_json)
                )
                storage_inst.update_task_completed = AsyncMock()
                MockStorage.return_value = storage_inst

                captured_kwargs: dict[str, object] = {}

                async def capture_to_thread(fn: object, **kwargs: object) -> str:
                    for k, v in kwargs.items():
                        captured_kwargs[k] = v
                    return "draft-captured"

                with patch(
                    "src.services.worker_service.asyncio.to_thread",
                    side_effect=capture_to_thread,
                ):
                    with patch("src.services.worker_service.EmailService"):
                        await worker.process_send_draft(email_id)

        assert captured_kwargs.get("subject") == expected_subject
        assert captured_kwargs.get("body") == expected_body
        assert captured_kwargs.get("to") == "recipient@example.com"
        assert captured_kwargs.get("thread_id") == "thr-42"


# ---------------------------------------------------------------------------
# process_task_failure
# ---------------------------------------------------------------------------


class TestProcessTaskFailure:
    async def test_records_failed_task_and_updates_status(
        self, worker: WorkerService, mock_session_ctx: tuple[MagicMock, AsyncMock]
    ) -> None:
        """create_failed_task і update_task_status(failed) виконуються коректно."""
        mock_maker, _ = mock_session_ctx
        email_id = str(uuid.uuid4())
        exc = RuntimeError("db crash")

        with patch("src.services.worker_service.async_session_maker", mock_maker):
            with patch("src.services.worker_service.StorageService") as MockStorage:
                storage_inst = AsyncMock()
                fake_task = _make_task()
                storage_inst.get_task_by_email_id = AsyncMock(return_value=fake_task)
                storage_inst.create_failed_task = AsyncMock()
                storage_inst.update_task_status = AsyncMock()
                MockStorage.return_value = storage_inst

                await worker.process_task_failure(email_id, exc, "traceback here")

        storage_inst.create_failed_task.assert_awaited_once()
        call_kwargs = storage_inst.create_failed_task.call_args
        assert call_kwargs.kwargs["error_type"] == "RuntimeError"
        assert "db crash" in call_kwargs.kwargs["message"]
        assert call_kwargs.kwargs["stack"] == "traceback here"
        storage_inst.update_task_status.assert_awaited_once_with(
            fake_task.id, TaskStatusEnum.failed
        )

    async def test_skips_gracefully_when_task_not_found(
        self, worker: WorkerService, mock_session_ctx: tuple[MagicMock, AsyncMock]
    ) -> None:
        """Якщо task не знайдено — не кидати виняток, create_failed_task не викликається."""
        mock_maker, _ = mock_session_ctx
        email_id = str(uuid.uuid4())

        with patch("src.services.worker_service.async_session_maker", mock_maker):
            with patch("src.services.worker_service.StorageService") as MockStorage:
                storage_inst = AsyncMock()
                storage_inst.get_task_by_email_id = AsyncMock(return_value=None)
                MockStorage.return_value = storage_inst

                await worker.process_task_failure(email_id, Exception("err"), "")

        storage_inst.create_failed_task.assert_not_awaited()

    async def test_commit_not_called_when_task_missing(
        self, worker: WorkerService, mock_session_ctx: tuple[MagicMock, AsyncMock]
    ) -> None:
        """Якщо task відсутній — session.commit() не викликається."""
        mock_maker, mock_session = mock_session_ctx
        email_id = str(uuid.uuid4())

        with patch("src.services.worker_service.async_session_maker", mock_maker):
            with patch("src.services.worker_service.StorageService") as MockStorage:
                storage_inst = AsyncMock()
                storage_inst.get_task_by_email_id = AsyncMock(return_value=None)
                MockStorage.return_value = storage_inst

                await worker.process_task_failure(email_id, Exception("err"), "")

        mock_session.commit.assert_not_awaited()

    async def test_commit_called_when_task_found(
        self, worker: WorkerService, mock_session_ctx: tuple[MagicMock, AsyncMock]
    ) -> None:
        """session.commit() має бути викликано після запису failed task."""
        mock_maker, mock_session = mock_session_ctx
        email_id = str(uuid.uuid4())
        exc = ValueError("validation failed")

        with patch("src.services.worker_service.async_session_maker", mock_maker):
            with patch("src.services.worker_service.StorageService") as MockStorage:
                storage_inst = AsyncMock()
                storage_inst.get_task_by_email_id = AsyncMock(return_value=_make_task())
                storage_inst.create_failed_task = AsyncMock()
                storage_inst.update_task_status = AsyncMock()
                MockStorage.return_value = storage_inst

                await worker.process_task_failure(email_id, exc, "stack")

        mock_session.commit.assert_awaited_once()

    @pytest.mark.parametrize(
        "exception,expected_type",
        [
            (RuntimeError("crash"), "RuntimeError"),
            (ValueError("bad input"), "ValueError"),
            (KeyError("key"), "KeyError"),
            (Exception("generic"), "Exception"),
        ],
    )
    async def test_error_type_reflects_exception_class(
        self,
        worker: WorkerService,
        mock_session_ctx: tuple[MagicMock, AsyncMock],
        exception: Exception,
        expected_type: str,
    ) -> None:
        """error_type у create_failed_task відповідає класу виключення."""
        mock_maker, _ = mock_session_ctx
        email_id = str(uuid.uuid4())

        with patch("src.services.worker_service.async_session_maker", mock_maker):
            with patch("src.services.worker_service.StorageService") as MockStorage:
                storage_inst = AsyncMock()
                storage_inst.get_task_by_email_id = AsyncMock(return_value=_make_task())
                storage_inst.create_failed_task = AsyncMock()
                storage_inst.update_task_status = AsyncMock()
                MockStorage.return_value = storage_inst

                await worker.process_task_failure(email_id, exception, "")

        call_kwargs = storage_inst.create_failed_task.call_args
        assert call_kwargs.kwargs["error_type"] == expected_type

    async def test_empty_stack_trace_is_accepted(
        self, worker: WorkerService, mock_session_ctx: tuple[MagicMock, AsyncMock]
    ) -> None:
        """Порожній stack trace передається без помилок."""
        mock_maker, _ = mock_session_ctx
        email_id = str(uuid.uuid4())

        with patch("src.services.worker_service.async_session_maker", mock_maker):
            with patch("src.services.worker_service.StorageService") as MockStorage:
                storage_inst = AsyncMock()
                storage_inst.get_task_by_email_id = AsyncMock(return_value=_make_task())
                storage_inst.create_failed_task = AsyncMock()
                storage_inst.update_task_status = AsyncMock()
                MockStorage.return_value = storage_inst

                await worker.process_task_failure(email_id, Exception("e"), "")

        call_kwargs = storage_inst.create_failed_task.call_args
        assert call_kwargs.kwargs["stack"] == ""
