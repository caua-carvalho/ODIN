from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

TaskStatus = Literal["todo", "doing", "done"]
TaskPriority = Literal["low", "medium", "high"]


# --- Projects ---------------------------------------------------------------
class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = ""
    color: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    color: Optional[str] = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: str
    color: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectDetailResponse(ProjectResponse):
    task_count: int = 0
    done_count: int = 0


# --- Tasks ------------------------------------------------------------------
class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: Optional[str] = ""
    status: TaskStatus = "todo"
    priority: TaskPriority = "medium"


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    position: Optional[int] = None


class TaskReorderItem(BaseModel):
    id: str
    status: TaskStatus
    position: int


class TaskReorderRequest(BaseModel):
    tasks: list[TaskReorderItem]


class TaskResponse(BaseModel):
    id: str
    project_id: str
    title: str
    description: str
    status: TaskStatus
    priority: TaskPriority
    position: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Files ------------------------------------------------------------------
class ProjectFile(BaseModel):
    name: str
    path: str  # relative to the project root
    is_dir: bool
    size: int
    modified_at: datetime


class FileListResponse(BaseModel):
    path: str  # directory being listed, relative to the project root
    entries: list[ProjectFile]


class MkdirRequest(BaseModel):
    path: str = Field(min_length=1)
