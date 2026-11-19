from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.core.database import SessionDep
from app.modules.tasks import services
from app.modules.tasks.models import TaskStatus
from app.modules.tasks.schemas import (
    TaskCreate,
    TaskRead,
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
    task_status: Optional[TaskStatus] = Query(default=None, alias="status"),
    assignee_id: Optional[int] = Query(default=None),
    author_id: Optional[int] = Query(default=None),
) -> list[TaskRead]:
    _ = current_user
    return await services.list_tasks(
        session,
        status=task_status,
        assignee_id=assignee_id,
        author_id=author_id,
    )


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