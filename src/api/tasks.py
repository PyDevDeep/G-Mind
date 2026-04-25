"""Task management API endpoints.

Roadmap requirement: src/api/tasks.py
- GET  /tasks/{id}       → TaskResponse
- POST /tasks/{id}/retry → Manual retry
- GET  /tasks?status=    → List tasks filtered by status
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.dependencies import get_db_session, redis_client
from src.models.task import TaskStatusEnum
from src.schemas.task import TaskBrief, TaskResponse, TaskRetryResponse
from src.services.queue_service import QueueService
from src.services.storage_service import StorageService
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["Tasks"])


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> TaskResponse:
    """Return a single task with its associated email summary."""
    storage = StorageService(session)
    task = await storage.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return TaskResponse.model_validate(task)


@router.get("", response_model=list[TaskBrief])
async def list_tasks(
    status: str | None = Query(default=None, description="Filter by task status"),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
) -> list[TaskBrief]:
    """List tasks, optionally filtered by status."""
    storage = StorageService(session)

    status_enum: TaskStatusEnum | None = None
    if status is not None:
        try:
            status_enum = TaskStatusEnum(status)
        except ValueError as err:
            valid = [s.value for s in TaskStatusEnum]
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{status}'. Valid: {valid}",
            ) from err

    tasks = await storage.list_tasks(status=status_enum, limit=limit)
    return [TaskBrief.model_validate(t) for t in tasks]


@router.post("/{task_id}/retry", response_model=TaskRetryResponse)
async def retry_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> TaskRetryResponse:
    """Manually retry a failed task by resetting it to pending and re-dispatching."""
    storage = StorageService(session)
    task = await storage.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status != TaskStatusEnum.failed:
        raise HTTPException(
            status_code=409,
            detail=f"Only failed tasks can be retried. Current status: {task.status.value}",
        )

    queue = QueueService(session, redis_client)
    await queue.retry_failed_task(task.email_id)
    await session.commit()

    return TaskRetryResponse(
        task_id=task.id,
        status="pending",
        message="Task re-dispatched for processing",
    )
