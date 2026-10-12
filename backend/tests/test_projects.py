"""Project workspace tests.

Covers the project/task CRUD route logic and, above all, the path-safety
guarantees of the per-project file workspace: slugs, traversal rejection and
file upload/list/delete against a throwaway workspace directory.
"""
import sys
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile

# Make sure we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

import app.config as config_module
from app.api.routes import projects
from app.database.models import Base
from app.projects import service as project_service
from app.schemas.project import (
    MkdirRequest,
    ProjectCreate,
    ProjectUpdate,
    TaskCreate,
    TaskReorderItem,
    TaskReorderRequest,
    TaskUpdate,
)


async def _make_session(tmp_path):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Point the projects root at an isolated temporary workspace.

    Patches the shared settings singleton so both the service and `PathGuard`
    (used by the agent tool) resolve paths inside the temp workspace.
    """
    ws = tmp_path / "workspace"
    ws.mkdir()
    monkeypatch.setattr(config_module.settings, "odin_workspace", str(ws))
    return ws


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
class TestSlugify:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("My Project", "my-project"),
            ("  Spaces  ", "spaces"),
            ("R&D / Notes!!", "r-d-notes"),
            ("UPPER_case.2026", "upper-case-2026"),
            ("...", "project"),
        ],
    )
    def test_slugify(self, name, expected):
        assert project_service.slugify(name) == expected


class TestSafeResolve:
    def _project(self, slug="demo"):
        return SimpleNamespace(slug=slug)

    def test_accepts_nested_path(self, workspace):
        project = self._project()
        resolved = project_service.resolve_path(project, "docs/report.pdf")
        assert resolved == workspace / "projects" / "demo" / "docs" / "report.pdf"

    def test_root_itself_is_allowed(self, workspace):
        project = self._project()
        resolved = project_service.resolve_path(project, "")
        assert resolved == workspace / "projects" / "demo"

    def test_rejects_parent_traversal(self, workspace):
        project = self._project()
        with pytest.raises(HTTPException) as exc:
            project_service.resolve_path(project, "../other-project/secret.txt")
        assert exc.value.status_code == 400

    def test_rejects_absolute_path(self, workspace):
        project = self._project()
        with pytest.raises(HTTPException) as exc:
            project_service.resolve_path(project, "/etc/passwd")
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# Project + task CRUD (route functions against a temp DB)
# ---------------------------------------------------------------------------
class TestProjectCrud:
    async def test_create_get_update_delete(self, workspace, tmp_path):
        engine, Session = await _make_session(tmp_path)
        try:
            async with Session() as db:
                project = await projects.create_project(
                    ProjectCreate(name="My Project", description="desc"), db=db
                )
                assert project.slug == "my-project"
                assert project.task_count == 0
                # Workspace directory was created on disk.
                assert (workspace / "projects" / "my-project").is_dir()

                fetched = await projects.get_project(project.id, db=db)
                assert fetched.name == "My Project"

                updated = await projects.update_project(
                    project.id, ProjectUpdate(name="Renamed"), db=db
                )
                assert updated.name == "Renamed"

            async with Session() as db:
                listing = await projects.list_projects(db=db)
                assert len(listing) == 1
                assert listing[0].name == "Renamed"

            async with Session() as db:
                deleted = await projects.delete_project(project.id, db=db)
                assert deleted["deleted"] == project.id
                assert not (workspace / "projects" / "my-project").exists()
                assert await projects.list_projects(db=db) == []
        finally:
            await engine.dispose()

    async def test_slug_collision_gets_suffix(self, workspace, tmp_path):
        engine, Session = await _make_session(tmp_path)
        try:
            async with Session() as db:
                first = await projects.create_project(ProjectCreate(name="Same"), db=db)
                second = await projects.create_project(ProjectCreate(name="Same"), db=db)
                assert first.slug == "same"
                assert second.slug == "same-2"
        finally:
            await engine.dispose()


class TestTaskCrud:
    async def _project(self, Session):
        async with Session() as db:
            return await projects.create_project(ProjectCreate(name="Tasks"), db=db)

    async def test_create_list_update_reorder_delete(self, workspace, tmp_path):
        engine, Session = await _make_session(tmp_path)
        try:
            project = await self._project(Session)

            async with Session() as db:
                t1 = await projects.create_task(
                    project.id, TaskCreate(title="First"), db=db
                )
                t2 = await projects.create_task(
                    project.id, TaskCreate(title="Second", status="doing"), db=db
                )
                assert t1.status == "todo"
                assert t2.status == "doing"

                tasks = await projects.list_tasks(project.id, db=db)
                assert {t.title for t in tasks} == {"First", "Second"}

                moved = await projects.update_task(
                    t1.id, TaskUpdate(status="done", priority="high"), db=db
                )
                assert moved.status == "done"
                assert moved.priority == "high"

                await projects.reorder_tasks(
                    project.id,
                    TaskReorderRequest(
                        tasks=[
                            TaskReorderItem(id=t2.id, status="todo", position=0),
                            TaskReorderItem(id=t1.id, status="done", position=1),
                        ]
                    ),
                    db=db,
                )

            async with Session() as db:
                reordered = await projects.list_tasks(project.id, db=db)
                assert [t.id for t in reordered] == [t2.id, t1.id]

                detail = await projects.get_project(project.id, db=db)
                assert detail.task_count == 2
                assert detail.done_count == 1

                await projects.delete_task(t2.id, db=db)
                remaining = await projects.list_tasks(project.id, db=db)
                assert [t.id for t in remaining] == [t1.id]
        finally:
            await engine.dispose()


# ---------------------------------------------------------------------------
# File workspace
# ---------------------------------------------------------------------------
class TestProjectFiles:
    async def _project(self, Session):
        async with Session() as db:
            return await projects.create_project(ProjectCreate(name="Files"), db=db)

    async def test_upload_list_download_delete(self, workspace, tmp_path):
        engine, Session = await _make_session(tmp_path)
        try:
            project = await self._project(Session)

            async with Session() as db:
                uploaded = await projects.upload_file(
                    project.id,
                    file=UploadFile(BytesIO(b"hello world"), filename="note.txt"),
                    path="docs",
                    db=db,
                )
                assert uploaded.path == "docs/note.txt"
                assert uploaded.size == 11

                listing = await projects.list_files(project.id, path="docs", db=db)
                assert [e.name for e in listing.entries] == ["note.txt"]
                assert listing.entries[0].is_dir is False

            # The bytes really landed inside the project workspace.
            assert (workspace / "projects" / "files" / "docs" / "note.txt").read_bytes() == b"hello world"

            async with Session() as db:
                await projects.delete_file(project.id, path="docs/note.txt", db=db)
                listing = await projects.list_files(project.id, path="docs", db=db)
                assert listing.entries == []
        finally:
            await engine.dispose()

    async def test_mkdir_and_list_dirs_first(self, workspace, tmp_path):
        engine, Session = await _make_session(tmp_path)
        try:
            project = await self._project(Session)
            async with Session() as db:
                created = await projects.make_directory(
                    project.id, MkdirRequest(path="assets"), db=db
                )
                assert created.is_dir is True

                listing = await projects.list_files(project.id, path="", db=db)
                assert listing.entries[0].name == "assets"
                assert listing.entries[0].is_dir is True
        finally:
            await engine.dispose()

    async def test_download_rejects_missing_file(self, workspace, tmp_path):
        engine, Session = await _make_session(tmp_path)
        try:
            project = await self._project(Session)
            async with Session() as db:
                with pytest.raises(HTTPException) as exc:
                    await projects.download_file(project.id, path="nope.txt", db=db)
                assert exc.value.status_code == 404
        finally:
            await engine.dispose()

    async def test_upload_cannot_escape_workspace(self, workspace, tmp_path):
        engine, Session = await _make_session(tmp_path)
        try:
            project = await self._project(Session)
            async with Session() as db:
                with pytest.raises(HTTPException) as exc:
                    await projects.upload_file(
                        project.id,
                        file=UploadFile(BytesIO(b"x"), filename="evil.txt"),
                        path="../../",
                        db=db,
                    )
                assert exc.value.status_code == 400
        finally:
            await engine.dispose()


# ---------------------------------------------------------------------------
# Agent tools
# ---------------------------------------------------------------------------
def _session_provider(Session):
    """Replace `get_db_session` with one bound to the temp engine."""

    @asynccontextmanager
    async def _provider():
        async with Session() as db:
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    return _provider


@pytest.fixture
async def project_tools(workspace, tmp_path, monkeypatch):
    """All project tools bound to a temp DB/workspace, keyed by tool name."""
    engine, Session = await _make_session(tmp_path)

    import app.tools.projects.tools as tools_module

    monkeypatch.setattr(tools_module, "get_db_session", _session_provider(Session))

    from app.security.path_guard import PathGuard
    from app.security.policy import SecurityPolicy

    security = SecurityPolicy(PathGuard())
    tool_map = {t.definition.name: t for t in tools_module.create_project_tools(security)}
    try:
        yield tool_map, Session
    finally:
        await engine.dispose()


class TestProjectTools:
    async def test_full_workflow(self, project_tools, workspace):
        tools, _ = project_tools

        created = await tools["create_project"].execute({"name": "Demo"}, "c")
        assert created.success, created.error
        assert created.output["slug"] == "demo"
        assert (workspace / "projects" / "demo").is_dir()

        listed = await tools["list_projects"].execute({}, "c")
        assert listed.output["count"] == 1

        fetched = await tools["get_project"].execute({"project": "Demo"}, "c")
        assert fetched.output["name"] == "Demo"

        updated = await tools["update_project"].execute(
            {"project": "demo", "description": "section"}, "c"
        )
        assert updated.output["description"] == "section"

        first = await tools["create_task"].execute(
            {"project": "Demo", "title": "Write docs", "priority": "high"}, "c"
        )
        assert first.output["status"] == "todo"
        assert first.output["priority"] == "high"

        second = await tools["create_task"].execute(
            {"project": "Demo", "title": "Fix bug", "status": "doing"}, "c"
        )
        assert second.output["status"] == "doing"

        tasks = await tools["list_tasks"].execute({"project": "Demo"}, "c")
        assert tasks.output["count"] == 2

        # Update by title, move by id.
        moved = await tools["update_task"].execute(
            {"project": "Demo", "task": "Write docs", "status": "done"}, "c"
        )
        assert moved.output["status"] == "done"

        moved2 = await tools["move_task"].execute(
            {"project": "Demo", "task": first.output["id"], "status": "doing"}, "c"
        )
        assert moved2.output["status"] == "doing"

        deleted_task = await tools["delete_task"].execute(
            {"project": "Demo", "task": "Fix bug"}, "c"
        )
        assert deleted_task.output["deleted"] == "Fix bug"
        remaining = await tools["list_tasks"].execute({"project": "Demo"}, "c")
        assert remaining.output["count"] == 1

        # Workspace files.
        written = await tools["write_project_file"].execute(
            {"project": "Demo", "path": "docs/readme.md", "content": "hello"}, "c"
        )
        assert written.output["path"] == "docs/readme.md"
        assert (workspace / "projects" / "demo" / "docs" / "readme.md").read_text() == "hello"

        read = await tools["read_project_file"].execute(
            {"project": "Demo", "path": "docs/readme.md"}, "c"
        )
        assert read.output["content"] == "hello"

        files = await tools["list_project_files"].execute(
            {"project": "Demo", "path": "docs"}, "c"
        )
        assert [e["name"] for e in files.output["entries"]] == ["readme.md"]

        folder = await tools["create_project_directory"].execute(
            {"project": "Demo", "path": "assets"}, "c"
        )
        assert folder.output["is_dir"] is True

        removed = await tools["delete_project_file"].execute(
            {"project": "Demo", "path": "assets"}, "c"
        )
        assert removed.output["deleted"] == "assets"

        deleted = await tools["delete_project"].execute({"project": "Demo"}, "c")
        assert deleted.success, deleted.error
        assert not (workspace / "projects" / "demo").exists()
        assert (await tools["list_projects"].execute({}, "c")).output["count"] == 0

    async def test_all_tools_are_registered(self, project_tools):
        tools, _ = project_tools
        assert set(tools) == {
            "list_projects",
            "get_project",
            "create_project",
            "update_project",
            "delete_project",
            "list_tasks",
            "create_task",
            "update_task",
            "move_task",
            "delete_task",
            "list_project_files",
            "read_project_file",
            "write_project_file",
            "create_project_directory",
            "delete_project_file",
        }
        assert all(t.definition.category == "projects" for t in tools.values())

    async def test_reference_resolution_and_errors(self, project_tools):
        tools, _ = project_tools
        await tools["create_project"].execute({"name": "Alpha"}, "c")
        await tools["create_project"].execute({"name": "Alpine"}, "c")

        ambiguous = await tools["get_project"].execute({"project": "Alp"}, "c")
        assert ambiguous.success is False
        assert "Multiple projects" in ambiguous.error

        missing = await tools["get_project"].execute({"project": "nope"}, "c")
        assert missing.success is False
        assert "not found" in missing.error.lower()

    async def test_validation_and_path_safety(self, project_tools):
        tools, _ = project_tools

        blank = await tools["create_project"].execute({"name": "   "}, "c")
        assert blank.success is False

        await tools["create_project"].execute({"name": "Safe"}, "c")

        escape = await tools["write_project_file"].execute(
            {"project": "Safe", "path": "../evil.txt", "content": "x"}, "c"
        )
        assert escape.success is False
        assert "escapes" in escape.error.lower()

        absolute = await tools["read_project_file"].execute(
            {"project": "Safe", "path": "/etc/passwd"}, "c"
        )
        assert absolute.success is False
        assert "absolute" in absolute.error.lower()

        empty_update = await tools["update_project"].execute({"project": "Safe"}, "c")
        assert empty_update.success is False


