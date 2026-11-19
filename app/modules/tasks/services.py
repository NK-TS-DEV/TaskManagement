from datetime import datetime, timezone
from typing import Literal, Optional

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tasks.models import Task, TaskPriority, TaskStatus
from app.modules.tasks.schemas import TaskCreate, TaskStatusUpdate, TaskUpdate
from app.modules.users.models import User


class TaskError(Exception):
    """Base exception for task business logic."""


class TaskNotFoundError(TaskError):
    """Task not found."""


class AssigneeNotFoundError(TaskError):
    """Specified assignee not found."""


class InvalidDeadlineError(TaskError):
    """Invalid deadline."""


class InvalidStatusTransitionError(TaskError):
    """Invalid status transition."""


class TaskLimitExceededError(TaskError):
    """Active tasks limit exceeded."""


class TaskUpdateForbiddenError(TaskError):
    """Task cannot be edited in its current state."""


class TaskDeleteForbiddenError(TaskError):
    """Task cannot be deleted in its current state."""


MAX_ACTIVE_TASKS_PER_USER = 10

ACTIVE_STATUSES: set[TaskStatus] = {
    TaskStatus.BACKLOG,
    TaskStatus.IN_PROGRESS,
    TaskStatus.REVIEW,
}

FINAL_STATUSES: set[TaskStatus] = {
    TaskStatus.DONE,
    TaskStatus.CANCELLED,
}

LOCKED_EDIT_STATUSES: set[TaskStatus] = {
    TaskStatus.DONE,
    TaskStatus.CANCELLED,
}

LOCKED_ASSIGNEE_STATUSES: set[TaskStatus] = {
    TaskStatus.REVIEW,
    TaskStatus.DONE,
}

FORBIDDEN_DELETE_STATUSES: set[TaskStatus] = {
    TaskStatus.IN_PROGRESS,
    TaskStatus.REVIEW,
}

ALLOWED_STATUS_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.BACKLOG: {
        TaskStatus.IN_PROGRESS,
        TaskStatus.CANCELLED,
    },
    TaskStatus.IN_PROGRESS: {
        TaskStatus.REVIEW,
        TaskStatus.CANCELLED,
    },
    TaskStatus.REVIEW: {
        TaskStatus.DONE,
        TaskStatus.CANCELLED,
    },
    TaskStatus.DONE: set(),
    TaskStatus.CANCELLED: set(),
}

SortByField = Literal["default", "created_at", "deadline", "priority"]
SortOrder = Literal["asc", "desc"]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _validate_deadline(deadline: Optional[datetime]) -> Optional[datetime]:
    """Deadline cannot be in the past or earlier than the current date."""
    if deadline is None:
        return None
    normalized = _normalize_to_utc(deadline)
    now = _now_utc()
    # Reject if timestamp is in the past OR calendar date is before today's UTC date
    if normalized <= now or normalized.date() < now.date():
        raise InvalidDeadlineError("Deadline cannot be in the past or before current date")
    return normalized


async def _ensure_assignee_exists(
    session: AsyncSession, assignee_id: Optional[int]
) -> None:
    if assignee_id is None:
        return
    assignee = await session.get(User, assignee_id)
    if assignee is None:
        raise AssigneeNotFoundError(f"User with id={assignee_id} not found")


async def _check_active_tasks_limit(
    session: AsyncSession, user_id: int
) -> None:
    stmt = select(func.count(Task.id)).where(
        or_(Task.author_id == user_id, Task.assignee_id == user_id),
        Task.status.in_(ACTIVE_STATUSES),
    )
    result = await session.execute(stmt)
    active_count = result.scalar_one()
    if active_count >= MAX_ACTIVE_TASKS_PER_USER:
        raise TaskLimitExceededError(
            f"Active tasks limit ({MAX_ACTIVE_TASKS_PER_USER}) reached"
        )


def _validate_status_transition(
    current_status: TaskStatus, new_status: TaskStatus
) -> None:
    if current_status == new_status:
        return
    allowed = ALLOWED_STATUS_TRANSITIONS.get(current_status, set())
    if new_status not in allowed:
        raise InvalidStatusTransitionError(
            f"Cannot transition task from '{current_status.value}' to '{new_status.value}'"
        )


def _validate_done_requirements(task: Task) -> None:
    if task.assignee_id is None:
        raise InvalidStatusTransitionError(
            "Cannot transition task to 'Done' without an assigned user"
        )
    if task.deadline is None or _normalize_to_utc(task.deadline) <= _now_utc():
        raise InvalidDeadlineError(
            "Cannot transition task to 'Done' when deadline is missing or already passed"
        )


def _priority_rank_expr():
    whens = []
    if hasattr(TaskPriority, "CRITICAL"):
        whens.append((Task.priority == TaskPriority.CRITICAL, 0))
    if hasattr(TaskPriority, "HIGH"):
        whens.append((Task.priority == TaskPriority.HIGH, 1))
    if hasattr(TaskPriority, "MEDIUM"):
        whens.append((Task.priority == TaskPriority.MEDIUM, 2))
    if hasattr(TaskPriority, "LOW"):
        whens.append((Task.priority == TaskPriority.LOW, 3))
    return case(*whens, else_=99)


async def get_task_by_id(session: AsyncSession, task_id: int) -> Task:
    task = await session.get(Task, task_id)
    if task is None:
        raise TaskNotFoundError(f"Task with id={task_id} not found")
    return task


async def list_tasks(
    session: AsyncSession,
    status: Optional[TaskStatus] = None,
    priority: Optional[TaskPriority] = None,
    assignee_id: Optional[int] = None,
    author_id: Optional[int] = None,
    deadline_from: Optional[datetime] = None,
    deadline_to: Optional[datetime] = None,
    search: Optional[str] = None,
    sort_by: SortByField = "default",
    sort_order: SortOrder = "asc",
    limit: int = 20,
    offset: int = 0,
) -> list[Task]:
    stmt = select(Task)

    if status is not None:
        stmt = stmt.where(Task.status == status)
    if priority is not None:
        stmt = stmt.where(Task.priority == priority)
    if assignee_id is not None:
        stmt = stmt.where(Task.assignee_id == assignee_id)
    if author_id is not None:
        stmt = stmt.where(Task.author_id == author_id)
    if deadline_from is not None:
        stmt = stmt.where(Task.deadline >= _normalize_to_utc(deadline_from))
    if deadline_to is not None:
        stmt = stmt.where(Task.deadline <= _normalize_to_utc(deadline_to))

    if search and search.strip():
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Task.title.ilike(pattern),
                Task.description.ilike(pattern),
            )
        )

    priority_rank = _priority_rank_expr()

    if sort_by == "created_at":
        order_col = Task.created_at.desc() if sort_order == "desc" else Task.created_at.asc()
        stmt = stmt.order_by(order_col, Task.id.desc())
    elif sort_by == "deadline":
        deadline_expr = (
            Task.deadline.desc().nullslast()
            if sort_order == "desc"
            else Task.deadline.asc().nullslast()
        )
        stmt = stmt.order_by(deadline_expr, Task.id.asc())
    elif sort_by == "priority":
        prio_expr = priority_rank.desc() if sort_order == "desc" else priority_rank.asc()
        stmt = stmt.order_by(prio_expr, Task.deadline.asc().nullslast(), Task.id.asc())
    else:
        stmt = stmt.order_by(
            priority_rank.asc(),
            Task.deadline.asc().nullslast(),
            Task.id.asc(),
        )

    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create_task(
    session: AsyncSession,
    data: TaskCreate,
    author_id: int,
) -> Task:
    validated_deadline = _validate_deadline(data.deadline)
    await _ensure_assignee_exists(session, data.assignee_id)

    if data.status == TaskStatus.DONE:
        temp_task = Task(
            title=data.title,
            assignee_id=data.assignee_id,
            deadline=validated_deadline,
        )
        _validate_done_requirements(temp_task)

    if data.status in ACTIVE_STATUSES:
        await _check_active_tasks_limit(session, author_id)

    task = Task(
        title=data.title,
        description=data.description,
        status=data.status,
        priority=data.priority,
        author_id=author_id,
        assignee_id=data.assignee_id,
        deadline=validated_deadline,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def update_task(
    session: AsyncSession,
    task_id: int,
    data: TaskUpdate,
) -> Task:
    task = await get_task_by_id(session, task_id)

    if task.status in LOCKED_EDIT_STATUSES:
        raise TaskUpdateForbiddenError(
            f"Cannot edit task in '{task.status.value}' status"
        )

    updates = data.model_dump(exclude_unset=True)

    if "assignee_id" in updates and updates["assignee_id"] != task.assignee_id:
        if task.status in LOCKED_ASSIGNEE_STATUSES:
            raise TaskUpdateForbiddenError(
                f"Cannot change assignee when task is in '{task.status.value}' status"
            )
        await _ensure_assignee_exists(session, updates["assignee_id"])

    if "deadline" in updates:
        updates["deadline"] = _validate_deadline(updates["deadline"])

    for field, value in updates.items():
        setattr(task, field, value)

    if updates:
        task.updated_at = _now_utc()

    await session.commit()
    await session.refresh(task)
    return task


async def change_task_status(
    session: AsyncSession,
    task_id: int,
    data: TaskStatusUpdate,
    actor_id: int,
) -> Task:
    task = await get_task_by_id(session, task_id)
    _validate_status_transition(task.status, data.status)

    if data.status == TaskStatus.DONE:
        _validate_done_requirements(task)

    if task.status not in ACTIVE_STATUSES and data.status in ACTIVE_STATUSES:
        await _check_active_tasks_limit(session, actor_id)

    task.status = data.status
    task.updated_at = _now_utc()
    await session.commit()
    await session.refresh(task)
    return task


async def delete_task(session: AsyncSession, task_id: int) -> None:
    task = await get_task_by_id(session, task_id)
    if task.status in FORBIDDEN_DELETE_STATUSES:
        raise TaskDeleteForbiddenError(
            f"Cannot delete task in '{task.status.value}' status"
        )
    await session.delete(task)
    await session.commit()


async def get_overdue_tasks(session: AsyncSession) -> list[Task]:
    now = _now_utc()
    stmt = (
        select(Task)
        .where(
            Task.deadline.is_not(None),
            Task.deadline < now,
            Task.status.notin_(FINAL_STATUSES),
        )
        .order_by(Task.deadline.asc(), Task.id.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_tasks_stats(session: AsyncSession) -> dict:
    now = _now_utc()
    result = await session.execute(select(Task))
    tasks = list(result.scalars().all())

    by_status: dict[str, int] = {s.value: 0 for s in TaskStatus}
    by_priority: dict[str, int] = {p.value: 0 for p in TaskPriority}

    overdue_count = 0
    active_count = 0

    for task in tasks:
        by_status[task.status.value] = by_status.get(task.status.value, 0) + 1
        by_priority[task.priority.value] = by_priority.get(task.priority.value, 0) + 1

        if task.status in ACTIVE_STATUSES:
            active_count += 1

        if (
            task.deadline is not None
            and _normalize_to_utc(task.deadline) < now
            and task.status not in FINAL_STATUSES
        ):
            overdue_count += 1

    return {
        "total_tasks": len(tasks),
        "by_status": by_status,
        "by_priority": by_priority,
        "overdue_tasks": overdue_count,
        "active_tasks": active_count,
    }


async def cancel_overdue_tasks(session: AsyncSession) -> int:
    overdue_tasks = await get_overdue_tasks(session)
    if not overdue_tasks:
        return 0

    now = _now_utc()
    for task in overdue_tasks:
        task.status = TaskStatus.CANCELLED
        task.updated_at = now

    await session.commit()
    return len(overdue_tasks)