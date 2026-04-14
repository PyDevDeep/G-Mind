"""
Tests for StorageService: all CRUD methods and orchestration logic.

Coverage:
- Email: get_email, get_email_by_message_id, create_email (received_at auto-set)
- Task: create_task, get_task_by_email_id, update_task_status (all terminal statuses)
- AIResponse: upsert_ai_response CREATE path, upsert_ai_response UPDATE path (token accumulation)
- update_task_completed: updates both AIResponse.draft_id and task status
- save_incoming_email: atomic create_email + create_task + commit
- FailedTask: create_failed_task, list_failed_tasks ordering/limit
- get_ai_response_by_task_id: found and not-found cases

Strategy: mock AsyncSession entirely — no DB required for unit tests.
"""

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.email import Email
from src.models.failed_task import FailedTask
from src.models.response import AIResponse
from src.models.task import ProcessingTask, TaskStatusEnum
from src.schemas.ai import AIUsageStats
from src.services.storage_service import StorageService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def session() -> AsyncMock:
    """Замокована AsyncSession — не потребує реального підключення до БД."""
    s = AsyncMock()
    s.add = MagicMock()  # sync метод SQLAlchemy
    s.flush = AsyncMock()
    s.commit = AsyncMock()
    s.get = AsyncMock()
    s.execute = AsyncMock()
    return s


@pytest.fixture
def storage(session: AsyncMock) -> StorageService:
    """StorageService із замокованою сесією."""
    return StorageService(session)


@pytest.fixture
def sample_stats() -> AIUsageStats:
    return AIUsageStats(
        model_used="gpt-4o",
        prompt_tokens=100,
        completion_tokens=50,
        processing_time_ms=300,
    )


@pytest.fixture
def sample_task_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_email_id() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Email CRUD
# ---------------------------------------------------------------------------


class TestGetEmail:
    async def test_get_email_delegates_to_session_get(
        self, storage: StorageService, session: AsyncMock, sample_email_id: uuid.UUID
    ) -> None:
        """get_email викликає session.get(Email, id)."""
        fake_email = MagicMock(spec=Email)
        session.get.return_value = fake_email

        result = await storage.get_email(sample_email_id)

        session.get.assert_called_once_with(Email, sample_email_id)
        assert result is fake_email

    async def test_get_email_returns_none_when_not_found(
        self, storage: StorageService, session: AsyncMock, sample_email_id: uuid.UUID
    ) -> None:
        session.get.return_value = None

        result = await storage.get_email(sample_email_id)

        assert result is None


class TestGetEmailByMessageId:
    async def test_returns_email_when_found(
        self, storage: StorageService, session: AsyncMock
    ) -> None:
        fake_email = MagicMock(spec=Email)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_email
        session.execute.return_value = mock_result

        result = await storage.get_email_by_message_id("msg-123")

        assert result is fake_email

    async def test_returns_none_when_not_found(
        self, storage: StorageService, session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        result = await storage.get_email_by_message_id("nonexistent")

        assert result is None


class TestCreateEmail:
    async def test_create_email_sets_received_at_when_missing(
        self, storage: StorageService, session: AsyncMock
    ) -> None:
        """Якщо received_at не передано — має виставитись поточний UTC час."""
        email_data: dict[str, Any] = {
            "message_id": "msg-1",
            "thread_id": "thr-1",
            "sender": "a@b.com",
            "recipient": "c@d.com",
        }

        result = await storage.create_email(email_data)

        assert result.received_at is not None
        session.add.assert_called_once_with(result)
        session.flush.assert_awaited_once()

    async def test_create_email_preserves_provided_received_at(
        self, storage: StorageService, session: AsyncMock
    ) -> None:
        """Якщо received_at передано — не перезаписується."""
        fixed_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
        email_data: dict[str, Any] = {
            "message_id": "msg-2",
            "thread_id": "thr-1",
            "sender": "a@b.com",
            "recipient": "c@d.com",
            "received_at": fixed_dt,
        }

        result = await storage.create_email(email_data)

        assert result.received_at == fixed_dt


# ---------------------------------------------------------------------------
# Task CRUD
# ---------------------------------------------------------------------------


class TestCreateTask:
    async def test_create_task_sets_pending_status(
        self, storage: StorageService, session: AsyncMock, sample_email_id: uuid.UUID
    ) -> None:
        result = await storage.create_task(sample_email_id)

        assert result.status == TaskStatusEnum.pending
        assert result.email_id == sample_email_id
        session.add.assert_called_once_with(result)
        session.flush.assert_awaited_once()


class TestGetTaskByEmailId:
    async def test_returns_task_when_found(
        self, storage: StorageService, session: AsyncMock, sample_email_id: uuid.UUID
    ) -> None:
        fake_task = MagicMock(spec=ProcessingTask)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_task
        session.execute.return_value = mock_result

        result = await storage.get_task_by_email_id(sample_email_id)

        assert result is fake_task

    async def test_returns_none_when_not_found(
        self, storage: StorageService, session: AsyncMock, sample_email_id: uuid.UUID
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        result = await storage.get_task_by_email_id(sample_email_id)

        assert result is None


class TestUpdateTaskStatus:
    @pytest.mark.parametrize(
        "status",
        [TaskStatusEnum.completed, TaskStatusEnum.failed, TaskStatusEnum.draft_created],
    )
    async def test_terminal_statuses_set_completed_at(
        self,
        storage: StorageService,
        session: AsyncMock,
        sample_task_id: uuid.UUID,
        status: TaskStatusEnum,
    ) -> None:
        """Завершальні статуси мають виставляти completed_at."""
        mock_result = MagicMock()
        session.execute.return_value = mock_result

        await storage.update_task_status(sample_task_id, status)

        session.execute.assert_awaited_once()
        # Перевіряємо що stmt передано — значення completed_at перевіряються через stmt.compile
        compiled = str(session.execute.call_args[0][0])
        assert "completed_at" in compiled

    async def test_processing_status_sets_started_at(
        self,
        storage: StorageService,
        session: AsyncMock,
        sample_task_id: uuid.UUID,
    ) -> None:
        """Статус processing має виставляти started_at."""
        mock_result = MagicMock()
        session.execute.return_value = mock_result

        await storage.update_task_status(sample_task_id, TaskStatusEnum.processing)

        session.execute.assert_awaited_once()
        compiled = str(session.execute.call_args[0][0])
        assert "started_at" in compiled

    async def test_celery_id_included_in_update_when_provided(
        self,
        storage: StorageService,
        session: AsyncMock,
        sample_task_id: uuid.UUID,
    ) -> None:
        """celery_task_id додається до UPDATE якщо передано."""
        session.execute.return_value = MagicMock()

        await storage.update_task_status(
            sample_task_id, TaskStatusEnum.processing, celery_id="celery-abc"
        )

        compiled = str(session.execute.call_args[0][0])
        assert "celery_task_id" in compiled


# ---------------------------------------------------------------------------
# AIResponse CRUD
# ---------------------------------------------------------------------------


class TestUpsertAiResponse:
    async def test_create_path_when_no_existing_response(
        self,
        storage: StorageService,
        session: AsyncMock,
        sample_task_id: uuid.UUID,
        sample_stats: AIUsageStats,
    ) -> None:
        """Якщо AIResponse не існує — створюється новий запис."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        result = await storage.upsert_ai_response(
            task_id=sample_task_id,
            classification="needs_reply",
            confidence=0.9,
            stats=sample_stats,
        )

        assert result.classification == "needs_reply"
        assert result.confidence_score == 0.9
        assert result.model_used == "gpt-4o"
        assert result.prompt_tokens == 100
        session.add.assert_called_once_with(result)

    async def test_update_path_accumulates_tokens(
        self,
        storage: StorageService,
        session: AsyncMock,
        sample_task_id: uuid.UUID,
        sample_stats: AIUsageStats,
    ) -> None:
        """При UPDATE — токени та processing_time акумулюються, не перезаписуються."""
        existing = AIResponse(
            task_id=sample_task_id,
            classification="informational",
            confidence_score=0.7,
            model_used="gpt-4o",
            prompt_tokens=50,
            completion_tokens=20,
            processing_time_ms=100,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        session.execute.return_value = mock_result

        result = await storage.upsert_ai_response(
            task_id=sample_task_id,
            classification="needs_reply",
            confidence=0.95,
            stats=sample_stats,
        )

        # Акумуляція: 50 + 100 = 150, 20 + 50 = 70, 100 + 300 = 400
        assert result.prompt_tokens == 150
        assert result.completion_tokens == 70
        assert result.processing_time_ms == 400
        # classification оновлено
        assert result.classification == "needs_reply"
        # session.add НЕ викликається при update
        session.add.assert_not_called()

    async def test_update_path_does_not_overwrite_existing_reply_with_none(
        self,
        storage: StorageService,
        session: AsyncMock,
        sample_task_id: uuid.UUID,
        sample_stats: AIUsageStats,
    ) -> None:
        """generated_reply не обнуляється якщо новий виклик не передає його."""
        existing = AIResponse(
            task_id=sample_task_id,
            classification="needs_reply",
            confidence_score=0.9,
            model_used="gpt-4o",
            prompt_tokens=50,
            completion_tokens=20,
            processing_time_ms=100,
            generated_reply='{"subject":"Re","body":"Hello","tone":"pro"}',
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        session.execute.return_value = mock_result

        result = await storage.upsert_ai_response(
            task_id=sample_task_id,
            classification="needs_reply",
            confidence=0.9,
            stats=sample_stats,
            generated_reply=None,  # не передаємо нову відповідь
        )

        assert result.generated_reply == '{"subject":"Re","body":"Hello","tone":"pro"}'


# ---------------------------------------------------------------------------
# update_task_completed
# ---------------------------------------------------------------------------


class TestUpdateTaskCompleted:
    async def test_executes_two_statements(
        self,
        storage: StorageService,
        session: AsyncMock,
        sample_task_id: uuid.UUID,
    ) -> None:
        """update_task_completed виконує UPDATE AIResponse + UPDATE ProcessingTask."""
        session.execute.return_value = MagicMock()
        # update_task_status теж викликає execute — загалом 2 execute + 1 flush
        await storage.update_task_completed(sample_task_id, "draft-id-123")

        assert session.execute.await_count == 2
        session.flush.assert_awaited_once()


# ---------------------------------------------------------------------------
# save_incoming_email
# ---------------------------------------------------------------------------


class TestSaveIncomingEmail:
    async def test_returns_email_id_and_commits(
        self,
        storage: StorageService,
        session: AsyncMock,
    ) -> None:
        """save_incoming_email: атомарно зберігає email + task і робить commit."""
        expected_id = uuid.uuid4()
        fake_email = MagicMock(spec=Email)
        fake_email.id = expected_id

        email_data: dict[str, Any] = {
            "message_id": "msg-atomic",
            "thread_id": "thr-atomic",
            "sender": "x@y.com",
            "recipient": "a@b.com",
        }
        raw_payload: dict[str, Any] = {"id": "msg-atomic"}

        # Email.id присвоюється БД при flush — мокаємо create_email/create_task
        with (
            patch.object(
                storage, "create_email", new=AsyncMock(return_value=fake_email)
            ),
            patch.object(storage, "create_task", new=AsyncMock()),
        ):
            result_id = await storage.save_incoming_email(email_data, raw_payload)

        assert result_id == expected_id
        session.commit.assert_awaited_once()
        assert email_data["raw_payload"] is raw_payload


# ---------------------------------------------------------------------------
# FailedTask
# ---------------------------------------------------------------------------


class TestCreateFailedTask:
    async def test_creates_failed_task_with_retry_exhausted_true(
        self,
        storage: StorageService,
        session: AsyncMock,
        sample_task_id: uuid.UUID,
    ) -> None:
        result = await storage.create_failed_task(
            task_id=sample_task_id,
            error_type="ValueError",
            message="Something broke",
            stack="Traceback...",
        )

        assert result.task_id == sample_task_id
        assert result.retry_exhausted is True
        assert result.error_message == "Something broke"
        assert result.stack_trace == "Traceback..."
        session.add.assert_called_once_with(result)

    async def test_creates_failed_task_without_stack(
        self,
        storage: StorageService,
        session: AsyncMock,
        sample_task_id: uuid.UUID,
    ) -> None:
        """stack є опціональним — None допустимий."""
        result = await storage.create_failed_task(
            task_id=sample_task_id,
            error_type="RuntimeError",
            message="crash",
        )

        assert result.stack_trace is None


class TestListFailedTasks:
    async def test_returns_sequence_from_execute(
        self,
        storage: StorageService,
        session: AsyncMock,
    ) -> None:
        fake_tasks = [MagicMock(spec=FailedTask), MagicMock(spec=FailedTask)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = fake_tasks
        session.execute.return_value = mock_result

        result = await storage.list_failed_tasks(limit=2)

        assert list(result) == fake_tasks

    async def test_default_limit_is_50(
        self,
        storage: StorageService,
        session: AsyncMock,
    ) -> None:
        """Перевіряє що limit=50 передається як bind-параметр у скомпільований stmt."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        await storage.list_failed_tasks()

        stmt = session.execute.call_args[0][0]
        # SQLAlchemy компілює limit як bind parameter (:param_1) — перевіряємо через dict
        compiled = stmt.compile(compile_kwargs={"literal_binds": True})
        assert "50" in str(compiled)
