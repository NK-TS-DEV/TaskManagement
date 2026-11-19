from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.modules.tasks.models import TaskPriority, TaskStatus


class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee_id: Optional[int] = None
    deadline: Optional[datetime] = None


class TaskCreate(TaskBase):
    status: TaskStatus = TaskStatus.BACKLOG


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    priority: Optional[TaskPriority] = None
    assignee_id: Optional[int] = None
    deadline: Optional[datetime] = None


class TaskStatusUpdate(BaseModel):
    status: TaskStatus


class TaskRead(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: TaskStatus
    author_id: int
    created_at: datetime
    updated_at: datetime


class TaskStatsRead(BaseModel):
    total_tasks: int
    by_status: dict[str, int]
    by_priority: dict[str, int]
    overdue_tasks: int
    active_tasks: int