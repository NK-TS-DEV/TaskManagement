from fastapi import APIRouter, HTTPException, status

from app.core.database import SessionDep
from app.modules.comments import services
from app.modules.comments.schemas import CommentCreate, CommentRead
from app.modules.tasks.services import TaskNotFoundError
from app.modules.users.dependencies import CurrentUser

router = APIRouter(prefix="/tasks/{task_id}/comments", tags=["Comments"])


@router.post("", response_model=CommentRead, status_code=status.HTTP_201_CREATED)
async def create_comment_endpoint(
    task_id: int,
    data: CommentCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> CommentRead:
    try:
        return await services.create_comment(
            session,
            task_id=task_id,
            author_id=current_user.id,
            data=data,
        )
    except TaskNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get("", response_model=list[CommentRead])
async def list_comments_endpoint(
    task_id: int,
    session: SessionDep,
    current_user: CurrentUser,
) -> list[CommentRead]:
    _ = current_user
    try:
        return await services.list_task_comments(session, task_id=task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc