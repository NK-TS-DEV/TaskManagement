from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.core.database import SessionDep
from app.modules.tasks import services
from app.modules.tasks.models import TaskPriority, TaskStatus
from app.modules.tasks.schemas import (
    TaskCreate,
    TaskRead,
    TaskStatsRead,
    TaskStatusUpdate,
    TaskUpdate,
)
from app.modules.users.dependencies import CurrentUser

router = APIRouter(prefix="/tasks", tags=["Tasks"])


def _handle_task_error(exc: services.TaskError) -> HTTPException:
    if isinstance(exc, (services.TaskNotFoundError, services.AssigneeNotFoundError)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(
        exc,
        (
            services.InvalidDeadlineError,
            services.InvalidStatusTransitionError,
            services.TaskLimitExceededError,
            services.TaskUpdateForbiddenError,
            services.TaskDeleteForbiddenError,
        ),
    ):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task_endpoint(
    data: TaskCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> TaskRead:
    try:
        return await services.create_task(session, data=data, author_id=current_user.id)
    except services.TaskError as exc:
        raise _handle_task_error(exc) from exc


@router.get("", response_model=list[TaskRead])
async def list_tasks_endpoint(
    session: SessionDep,
    current_user: CurrentUser,
    search: Optional[str] = Query(default=None, description="Search in title and description"),
    task_status: Optional[TaskStatus] = Query(default=None, alias="status"),
    priority: Optional[TaskPriority] = Query(default=None),
    assignee_id: Optional[int] = Query(default=None),
    author_id: Optional[int] = Query(default=None),
    deadline_from: Optional[datetime] = Query(default=None),
    deadline_to: Optional[datetime] = Query(default=None),
    sort_by: services.SortByField = Query(default="default"),
    sort_order: services.SortOrder = Query(default="asc"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[TaskRead]:
    _ = current_user
    return await services.list_tasks(
        session,
        status=task_status,
        priority=priority,
        assignee_id=assignee_id,
        author_id=author_id,
        deadline_from=deadline_from,
        deadline_to=deadline_to,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )


@router.get("/overdue", response_model=list[TaskRead])
async def get_overdue_tasks_endpoint(
    session: SessionDep,
    current_user: CurrentUser,
) -> list[TaskRead]:
    _ = current_user
    return await services.get_overdue_tasks(session)


@router.get("/stats", response_model=TaskStatsRead)
async def get_tasks_stats_endpoint(
    session: SessionDep,
    current_user: CurrentUser,
) -> TaskStatsRead:
    _ = current_user
    stats = await services.get_tasks_stats(session)
    return TaskStatsRead(**stats)


@router.get("/{task_id}", response_model=TaskRead)
async def get_task_endpoint(
    task_id: int,
    session: SessionDep,
    current_user: CurrentUser,
) -> TaskRead:
    _ = current_user
    try:
        return await services.get_task_by_id(session, task_id=task_id)
    except services.TaskError as exc:
        raise _handle_task_error(exc) from exc


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task_endpoint(
    task_id: int,
    data: TaskUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> TaskRead:
    _ = current_user
    try:
        return await services.update_task(session, task_id=task_id, data=data)
    except services.TaskError as exc:
        raise _handle_task_error(exc) from exc


@router.patch("/{task_id}/status", response_model=TaskRead)
async def change_task_status_endpoint(
    task_id: int,
    data: TaskStatusUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> TaskRead:
    try:
        return await services.change_task_status(
            session,
            task_id=task_id,
            data=data,
            actor_id=current_user.id,
        )
    except services.TaskError as exc:
        raise _handle_task_error(exc) from exc


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task_endpoint(
    task_id: int,
    session: SessionDep,
    current_user: CurrentUser,
) -> None:
    _ = current_user
    try:
        await services.delete_task(session, task_id=task_id)
    except services.TaskError as exc:
        raise _handle_task_error(exc) from exc