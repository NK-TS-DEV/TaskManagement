from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.comments.models import Comment
from app.modules.comments.schemas import CommentCreate
from app.modules.tasks.services import get_task_by_id


async def create_comment(
    session: AsyncSession,
    task_id: int,
    author_id: int,
    data: CommentCreate,
) -> Comment:
    """Adds a new comments to an existing tasks."""
    await get_task_by_id(session, task_id)

    comment = Comment(
        content=data.content,
        task_id=task_id,
        author_id=author_id,
    )
    session.add(comment)
    await session.commit()
    await session.refresh(comment)
    return comment


async def list_task_comments(
    session: AsyncSession,
    task_id: int,
) -> list[Comment]:
    """Returns all comments for a given tasks ordered from oldest to newest."""
    await get_task_by_id(session, task_id)

    stmt = (
        select(Comment)
        .where(Comment.task_id == task_id)
        .order_by(Comment.created_at.asc(), Comment.id.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())