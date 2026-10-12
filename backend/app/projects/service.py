"""Project domain logic shared by the REST API and the agent tools.

Everything that touches a project — slug generation, task boards and the
on-disk file workspace — lives here so the HTTP routes
(`app/api/routes/projects.py`) and the agent tools
(`app/tools/projects/tools.py`) behave identically.

Functions raise ``fastapi.HTTPException`` for expected failures (404/400/409);
callers that are not HTTP routes (i.e. tools) translate them into tool errors.
"""
import re
import shutil
import uuid
from datetime import datetime, UTC
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import case, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import Project, Task
from app.schemas.project import FileListResponse, ProjectFile

PROJECTS_SUBDIR = "projects"
DEFAULT_PROJECT_COLOR = "#7c3aed"
VALID_COLUMNS = ("todo", "doing", "done")
VALID_PRIORITIES = ("low", "medium", "high")
MAX_TEXT_READ_BYTES = 1_000_000  # 1 MB


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
def slugify(name: str) -> str:
    """Turn a project name into a filesystem-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "project"


def projects_root() -> Path:
    """Directory that holds every project workspace."""
    return Path(settings.odin_workspace).expanduser().resolve() / PROJECTS_SUBDIR


def project_root(project: Project) -> Path:
    """On-disk workspace directory for a single project."""
    return projects_root() / project.slug


def relative_to_project(project: Project, path: Path) -> str:
    """Return `path` relative to the project root ("" for the root itself)."""
    root = project_root(project).resolve()
    resolved = path.resolve()
    if resolved == root:
        return ""
    try:
        return str(resolved.relative_to(root))
    except ValueError:
        return ""


def resolve_path(project: Project, rel_path: str) -> Path:
    """Resolve a user-supplied path, rejecting anything outside the project.

    Uses canonical resolution so `..`, absolute paths and symlink targets that
    escape the project root are all rejected.
    """
    root = project_root(project).resolve()
    raw = (rel_path or "").strip()
    if raw.startswith("/") or Path(raw).is_absolute():
        raise HTTPException(status_code=400, detail="Absolute paths are not allowed")
    candidate = (root / raw).resolve()
    if candidate != root and root not in candidate.parents:
        raise HTTPException(status_code=400, detail="Path escapes the project workspace")
    return candidate


def stat_file(project: Project, path: Path, is_dir: bool | None = None) -> ProjectFile:
    """Build a `ProjectFile` entry describing a path inside the workspace."""
    stat = path.stat()
    return ProjectFile(
        name=path.name,
        path=relative_to_project(project, path),
        is_dir=path.is_dir() if is_dir is None else is_dir,
        size=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime, UTC),
    )


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------
async def unique_slug(db: AsyncSession, name: str) -> str:
    """Slug derived from `name`, suffixed with -2/-3... on collision."""
    base = slugify(name)
    slug = base
    suffix = 2
    while True:
        existing = await db.execute(select(Project.id).where(Project.slug == slug))
        if existing.scalar_one_or_none() is None:
            return slug
        slug = f"{base}-{suffix}"
        suffix += 1


async def create_project(
    db: AsyncSession,
    *,
    name: str,
    description: str = "",
    color: str | None = None,
) -> Project:
    """Persist a project and create its workspace directory."""
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required")

    slug = await unique_slug(db, name)
    now = datetime.now(UTC)
    project = Project(
        id=str(uuid.uuid4()),
        name=name,
        slug=slug,
        description=description or "",
        color=color or DEFAULT_PROJECT_COLOR,
        created_at=now,
        updated_at=now,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    project_root(project).mkdir(parents=True, exist_ok=True)
    return project


async def list_projects(db: AsyncSession) -> list[Project]:
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    return list(result.scalars().all())


async def get_project(db: AsyncSession, project_id: str) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def get_project_by_reference(db: AsyncSession, reference: str | None) -> Project:
    """Resolve a project by id, slug, exact name, or an unambiguous partial name."""
    ref = (reference or "").strip()
    if not ref:
        raise HTTPException(status_code=400, detail="A project name or id is required")

    projects = await list_projects(db)

    for project in projects:
        if project.id == ref:
            return project
    for project in projects:
        if project.slug == ref:
            return project

    wanted_slug = slugify(ref)
    exact = [
        p for p in projects if p.name.lower() == ref.lower() or p.slug == wanted_slug
    ]
    if len(exact) == 1:
        return exact[0]

    candidates = exact or [p for p in projects if ref.lower() in p.name.lower()]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        names = ", ".join(f"'{p.name}'" for p in candidates)
        raise HTTPException(
            status_code=400,
            detail=f"Multiple projects match '{ref}': {names}. Use the project id.",
        )
    raise HTTPException(status_code=404, detail=f"Project not found: {ref}")


async def update_project(
    db: AsyncSession, project_id: str, changes: dict
) -> Project:
    project = await get_project(db, project_id)
    if changes.get("name") is not None and not str(changes["name"]).strip():
        raise HTTPException(status_code=400, detail="Project name cannot be empty")
    for field in ("name", "description", "color"):
        value = changes.get(field)
        if value is not None:
            setattr(project, field, value)
    project.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(project)
    return project


async def delete_project(db: AsyncSession, project_id: str) -> None:
    project = await get_project(db, project_id)
    root = project_root(project)

    await db.execute(delete(Task).where(Task.project_id == project_id))
    await db.delete(project)
    await db.commit()

    if root.exists():
        shutil.rmtree(root, ignore_errors=True)


async def project_counts(db: AsyncSession, project_id: str) -> tuple[int, int]:
    result = await db.execute(
        select(
            func.count(Task.id),
            func.sum(case((Task.status == "done", 1), else_=0)),
        ).where(Task.project_id == project_id)
    )
    total, done = result.one()
    return int(total or 0), int(done or 0)


async def all_project_counts(db: AsyncSession) -> dict[str, tuple[int, int]]:
    result = await db.execute(
        select(
            Task.project_id,
            func.count(Task.id),
            func.sum(case((Task.status == "done", 1), else_=0)),
        ).group_by(Task.project_id)
    )
    return {
        project_id: (int(total or 0), int(done or 0))
        for project_id, total, done in result.all()
    }


# ---------------------------------------------------------------------------
# Tasks (shared by the TODO list and the Kanban board)
# ---------------------------------------------------------------------------
def validate_status(status: str) -> None:
    if status not in VALID_COLUMNS:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")


def validate_priority(priority: str) -> None:
    if priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"Invalid priority: {priority}")


async def list_tasks(db: AsyncSession, project_id: str) -> list[Task]:
    result = await db.execute(
        select(Task)
        .where(Task.project_id == project_id)
        .order_by(Task.position, Task.created_at)
    )
    return list(result.scalars().all())


async def get_task(db: AsyncSession, task_id: str) -> Task:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


async def _next_position(db: AsyncSession, project_id: str, status: str) -> int:
    result = await db.execute(
        select(func.max(Task.position)).where(
            Task.project_id == project_id, Task.status == status
        )
    )
    return int(result.scalar() or 0) + 1


async def create_task(
    db: AsyncSession,
    project_id: str,
    *,
    title: str,
    description: str = "",
    status: str = "todo",
    priority: str = "medium",
) -> Task:
    await get_project(db, project_id)
    title = (title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Task title is required")
    validate_status(status)
    validate_priority(priority)

    now = datetime.now(UTC)
    task = Task(
        id=str(uuid.uuid4()),
        project_id=project_id,
        title=title,
        description=description or "",
        status=status,
        priority=priority,
        position=await _next_position(db, project_id, status),
        created_at=now,
        updated_at=now,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def update_task(db: AsyncSession, task_id: str, changes: dict) -> Task:
    task = await get_task(db, task_id)
    if changes.get("status") is not None:
        validate_status(changes["status"])
    if changes.get("priority") is not None:
        validate_priority(changes["priority"])
    if changes.get("title") is not None and not str(changes["title"]).strip():
        raise HTTPException(status_code=400, detail="Task title cannot be empty")

    for field in ("title", "description", "status", "priority", "position"):
        value = changes.get(field)
        if value is not None:
            setattr(task, field, value)
    task.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(task)
    return task


async def delete_task(db: AsyncSession, task_id: str) -> None:
    task = await get_task(db, task_id)
    await db.delete(task)
    await db.commit()


async def move_task(db: AsyncSession, project_id: str, task_id: str, status: str) -> Task:
    """Move a task to the end of a Kanban column."""
    validate_status(status)
    task = await get_task(db, task_id)
    if task.project_id != project_id:
        raise HTTPException(status_code=404, detail="Task not found in this project")
    task.status = status
    task.position = await _next_position(db, project_id, status)
    task.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(task)
    return task


async def reorder_tasks(
    db: AsyncSession, project_id: str, items: list[tuple[str, str, int]]
) -> int:
    """Persist the new column/order for several cards at once (Kanban drop)."""
    await get_project(db, project_id)
    now = datetime.now(UTC)
    for task_id, status, position in items:
        validate_status(status)
        await db.execute(
            update(Task)
            .where(Task.id == task_id, Task.project_id == project_id)
            .values(status=status, position=position, updated_at=now)
        )
    await db.commit()
    return len(items)


# ---------------------------------------------------------------------------
# Project files (the project workspace on disk)
# ---------------------------------------------------------------------------
async def list_dir(db: AsyncSession, project: Project, path: str) -> FileListResponse:
    directory = resolve_path(project, path)
    rel = relative_to_project(project, directory)

    if not directory.exists():
        return FileListResponse(path=rel, entries=[])
    if not directory.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")

    entries: list[ProjectFile] = []
    for child in sorted(
        directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())
    ):
        try:
            entries.append(stat_file(project, child))
        except OSError:
            continue
    return FileListResponse(path=rel, entries=entries)


def write_text(
    project: Project, path: str, content: str, encoding: str = "utf-8"
) -> ProjectFile:
    root = project_root(project).resolve()
    target = resolve_path(project, path)
    if target == root:
        raise HTTPException(status_code=400, detail="A file path is required")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding=encoding)
    return stat_file(project, target, is_dir=False)


def read_text(project: Project, path: str) -> str:
    target = resolve_path(project, path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    size = target.stat().st_size
    if size > MAX_TEXT_READ_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File is too large to read as text ({size} bytes)",
        )
    raw = target.read_bytes()
    if b"\x00" in raw:
        raise HTTPException(
            status_code=400, detail="File appears to be binary and cannot be read as text"
        )
    return raw.decode("utf-8", errors="replace")


def write_upload(
    project: Project, directory: str, filename: str, data: bytes
) -> ProjectFile:
    dir_path = resolve_path(project, directory)
    dir_path.mkdir(parents=True, exist_ok=True)

    safe_name = Path(filename or "upload").name
    if not safe_name or safe_name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid filename")
    target = resolve_path(project, str(Path(directory or "") / safe_name))
    target.write_bytes(data)
    return stat_file(project, target, is_dir=False)


def make_directory(project: Project, path: str) -> ProjectFile:
    root = project_root(project).resolve()
    target = resolve_path(project, path)
    if target == root:
        raise HTTPException(status_code=400, detail="Cannot create the project root")
    if target.exists():
        raise HTTPException(status_code=409, detail="Path already exists")
    target.mkdir(parents=True)
    return stat_file(project, target, is_dir=True)


def delete_path(project: Project, path: str) -> None:
    root = project_root(project).resolve()
    target = resolve_path(project, path)
    if target == root:
        raise HTTPException(status_code=400, detail="Cannot delete the project root")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
