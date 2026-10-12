from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.projects import service as project_service
from app.schemas.project import (
    FileListResponse,
    MkdirRequest,
    ProjectCreate,
    ProjectDetailResponse,
    ProjectFile,
    ProjectUpdate,
    TaskCreate,
    TaskReorderRequest,
    TaskResponse,
    TaskUpdate,
)

router = APIRouter()


def _to_detail(project, total: int, done: int) -> ProjectDetailResponse:
    return ProjectDetailResponse(
        id=project.id,
        name=project.name,
        slug=project.slug,
        description=project.description or "",
        color=project.color,
        created_at=project.created_at,
        updated_at=project.updated_at,
        task_count=total,
        done_count=done,
    )


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------
@router.get("/projects", response_model=list[ProjectDetailResponse])
async def list_projects(db: AsyncSession = Depends(get_db)):
    projects = await project_service.list_projects(db)
    counts = await project_service.all_project_counts(db)
    return [_to_detail(project, *counts.get(project.id, (0, 0))) for project in projects]


@router.post("/projects", response_model=ProjectDetailResponse, status_code=201)
async def create_project(data: ProjectCreate, db: AsyncSession = Depends(get_db)):
    project = await project_service.create_project(
        db,
        name=data.name,
        description=data.description or "",
        color=data.color,
    )
    return _to_detail(project, 0, 0)


@router.get("/projects/{project_id}", response_model=ProjectDetailResponse)
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await project_service.get_project(db, project_id)
    total, done = await project_service.project_counts(db, project_id)
    return _to_detail(project, total, done)


@router.patch("/projects/{project_id}", response_model=ProjectDetailResponse)
async def update_project(
    project_id: str, data: ProjectUpdate, db: AsyncSession = Depends(get_db)
):
    project = await project_service.update_project(
        db, project_id, data.model_dump(exclude_unset=True)
    )
    total, done = await project_service.project_counts(db, project_id)
    return _to_detail(project, total, done)


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    await project_service.delete_project(db, project_id)
    return {"deleted": project_id}


# ---------------------------------------------------------------------------
# Tasks (shared by the TODO list and the Kanban board)
# ---------------------------------------------------------------------------
@router.get("/projects/{project_id}/tasks", response_model=list[TaskResponse])
async def list_tasks(project_id: str, db: AsyncSession = Depends(get_db)):
    await project_service.get_project(db, project_id)
    return await project_service.list_tasks(db, project_id)


@router.post("/projects/{project_id}/tasks", response_model=TaskResponse, status_code=201)
async def create_task(
    project_id: str, data: TaskCreate, db: AsyncSession = Depends(get_db)
):
    return await project_service.create_task(
        db,
        project_id,
        title=data.title,
        description=data.description or "",
        status=data.status,
        priority=data.priority,
    )


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str, data: TaskUpdate, db: AsyncSession = Depends(get_db)
):
    return await project_service.update_task(
        db, task_id, data.model_dump(exclude_unset=True)
    )


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, db: AsyncSession = Depends(get_db)):
    await project_service.delete_task(db, task_id)
    return {"deleted": task_id}


@router.post("/projects/{project_id}/tasks/reorder")
async def reorder_tasks(
    project_id: str, data: TaskReorderRequest, db: AsyncSession = Depends(get_db)
):
    """Persist the new column/order for several cards at once (Kanban drop)."""
    updated = await project_service.reorder_tasks(
        db, project_id, [(item.id, item.status, item.position) for item in data.tasks]
    )
    return {"updated": updated}


# ---------------------------------------------------------------------------
# Project files (the project workspace on disk)
# ---------------------------------------------------------------------------
@router.get("/projects/{project_id}/files", response_model=FileListResponse)
async def list_files(
    project_id: str,
    path: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    project = await project_service.get_project(db, project_id)
    return await project_service.list_dir(db, project, path)


@router.post("/projects/{project_id}/files", response_model=ProjectFile, status_code=201)
async def upload_file(
    project_id: str,
    file: UploadFile = File(...),
    path: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    project = await project_service.get_project(db, project_id)

    directory = project_service.resolve_path(project, path)
    directory.mkdir(parents=True, exist_ok=True)

    filename = Path(file.filename or "upload").name
    if not filename or filename in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid filename")

    target = project_service.resolve_path(project, str(Path(path or "") / filename))

    try:
        with target.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                handle.write(chunk)
    finally:
        await file.close()

    return project_service.stat_file(project, target, is_dir=False)


@router.get("/projects/{project_id}/files/download")
async def download_file(
    project_id: str,
    path: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
):
    project = await project_service.get_project(db, project_id)
    target = project_service.resolve_path(project, path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target, filename=target.name)


@router.post("/projects/{project_id}/files/mkdir", response_model=ProjectFile, status_code=201)
async def make_directory(
    project_id: str,
    data: MkdirRequest,
    db: AsyncSession = Depends(get_db),
):
    project = await project_service.get_project(db, project_id)
    return project_service.make_directory(project, data.path)


@router.delete("/projects/{project_id}/files")
async def delete_file(
    project_id: str,
    path: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
):
    project = await project_service.get_project(db, project_id)
    project_service.delete_path(project, path)
    return {"deleted": path}
