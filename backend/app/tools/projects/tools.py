"""Agent tools for managing Odin projects (TODO/Kanban board + file workspace).

The tools are thin wrappers around `app.projects.service`, which is also used
by the REST API, so the agent and the UI always agree. Projects can be
referenced by id, slug or name; tasks by id or title.
"""
import logging

from fastapi import HTTPException

from app.database.session import get_db_session
from app.projects import service as project_service
from app.security.policy import SecurityPolicy, OperationType
from app.tools.base import ToolDefinition, ToolResult

logger = logging.getLogger("odin.tools.projects")


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------
def _project_dict(project, counts: tuple[int, int] | None = None) -> dict:
    data = {
        "id": project.id,
        "name": project.name,
        "slug": project.slug,
        "description": project.description or "",
        "color": project.color,
    }
    if counts is not None:
        data["task_count"], data["done_count"] = counts
    return data


def _task_dict(task) -> dict:
    return {
        "id": task.id,
        "project_id": task.project_id,
        "title": task.title,
        "description": task.description or "",
        "status": task.status,
        "priority": task.priority,
        "position": task.position,
    }


def _file_dict(entry) -> dict:
    return {
        "name": entry.name,
        "path": entry.path,
        "is_dir": entry.is_dir,
        "size": entry.size,
        "modified_at": entry.modified_at.isoformat(),
    }


async def _resolve_task(db, project_id: str, reference: str):
    """Find a task inside a project by id or (partial) title."""
    ref = (reference or "").strip()
    if not ref:
        raise HTTPException(status_code=400, detail="A task id or title is required")

    tasks = await project_service.list_tasks(db, project_id)
    for task in tasks:
        if task.id == ref:
            return task

    exact = [t for t in tasks if t.title.lower() == ref.lower()]
    if len(exact) == 1:
        return exact[0]

    candidates = exact or [t for t in tasks if ref.lower() in t.title.lower()]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        titles = ", ".join(f"'{t.title}'" for t in candidates)
        raise HTTPException(
            status_code=400,
            detail=f"Multiple tasks match '{ref}': {titles}. Use the task id.",
        )
    raise HTTPException(status_code=404, detail=f"Task not found: {ref}")


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------
class ProjectToolBase:
    """Shared plumbing for the project tools.

    Project workspaces always live inside ODIN_WORKSPACE, so the security
    policy classifies them as ALLOW; the check below is a defensive guard.
    """

    def __init__(self, security: SecurityPolicy) -> None:
        self.security = security

    def _check(self, *paths) -> ToolResult | None:
        for path in paths:
            decision = self.security.check_file_operation(
                str(path), OperationType.WRITE
            )
            if self.security.is_denied(decision):
                return ToolResult(success=False, error=f"Access denied: {decision.reason}")
            if self.security.requires_approval(decision):
                return ToolResult(
                    success=False,
                    error=f"Operation requires authorization: {decision.reason}",
                )
        return None

    @staticmethod
    def _fail(exc: Exception) -> ToolResult:
        if isinstance(exc, HTTPException):
            return ToolResult(success=False, error=str(exc.detail))
        logger.exception("project tool failed")
        return ToolResult(success=False, error=str(exc))


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------
class ListProjectsTool(ProjectToolBase):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="list_projects",
            description=(
                "List every project with its id, name, slug, description and task "
                "counts. Use this to discover projects (and their ids/slugs) before "
                "creating tasks, files or acting on one."
            ),
            category="projects",
            parameters_schema={"type": "object", "properties": {}},
        )

    async def execute(self, arguments: dict, conversation_id: str) -> ToolResult:
        try:
            async with get_db_session() as db:
                projects = await project_service.list_projects(db)
                counts = await project_service.all_project_counts(db)
                output = [
                    _project_dict(p, counts.get(p.id, (0, 0))) for p in projects
                ]
        except Exception as exc:
            return self._fail(exc)
        return ToolResult(success=True, output={"projects": output, "count": len(output)})


class GetProjectTool(ProjectToolBase):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="get_project",
            description=(
                "Get a single project's details (id, slug, description, colour and "
                "task counts). Reference it by name, slug or id."
            ),
            category="projects",
            parameters_schema={
                "type": "object",
                "properties": {
                    "project": {
                        "type": "string",
                        "description": "Project name, slug or id.",
                    }
                },
                "required": ["project"],
            },
        )

    async def execute(self, arguments: dict, conversation_id: str) -> ToolResult:
        try:
            async with get_db_session() as db:
                project = await project_service.get_project_by_reference(
                    db, arguments.get("project")
                )
                counts = await project_service.project_counts(db, project.id)
                output = _project_dict(project, counts)
        except Exception as exc:
            return self._fail(exc)
        return ToolResult(success=True, output=output)


class CreateProjectTool(ProjectToolBase):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="create_project",
            description=(
                "Create a new project. Each project has a TODO list, a Kanban board "
                "and a file workspace on disk, and appears in the Projects tab. Use "
                "this when the user asks to create or start a project (e.g. 'create a "
                "project called X'). Returns the created project."
            ),
            category="projects",
            parameters_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Project name. Used to generate its workspace folder.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional short description of the project.",
                    },
                    "color": {
                        "type": "string",
                        "description": "Optional hex colour for the project, e.g. '#7c3aed'.",
                    },
                },
                "required": ["name"],
            },
        )

    async def execute(self, arguments: dict, conversation_id: str) -> ToolResult:
        name = (arguments.get("name") or "").strip()
        if not name:
            return ToolResult(success=False, error="A project name is required.")

        guard = self._check(project_service.projects_root())
        if guard:
            return guard

        try:
            async with get_db_session() as db:
                project = await project_service.create_project(
                    db,
                    name=name,
                    description=arguments.get("description") or "",
                    color=arguments.get("color") or None,
                )
                output = _project_dict(project, (0, 0))
                output["workspace"] = str(project_service.project_root(project))
        except Exception as exc:
            return self._fail(exc)
        logger.info("create_project: %s (%s)", output["name"], output["slug"])
        return ToolResult(success=True, output=output)


class UpdateProjectTool(ProjectToolBase):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="update_project",
            description=(
                "Rename a project or change its description/colour. Reference the "
                "project by name, slug or id. Only the fields you pass are changed."
            ),
            category="projects",
            parameters_schema={
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Project name, slug or id."},
                    "name": {"type": "string", "description": "New project name."},
                    "description": {"type": "string", "description": "New description."},
                    "color": {"type": "string", "description": "New hex colour, e.g. '#22c55e'."},
                },
                "required": ["project"],
            },
        )

    async def execute(self, arguments: dict, conversation_id: str) -> ToolResult:
        changes = {
            key: arguments[key]
            for key in ("name", "description", "color")
            if key in arguments and arguments[key] is not None
        }
        if not changes:
            return ToolResult(success=False, error="No changes were provided.")

        try:
            async with get_db_session() as db:
                project = await project_service.get_project_by_reference(
                    db, arguments.get("project")
                )
                project = await project_service.update_project(db, project.id, changes)
                counts = await project_service.project_counts(db, project.id)
                output = _project_dict(project, counts)
        except Exception as exc:
            return self._fail(exc)
        return ToolResult(success=True, output=output)


class DeleteProjectTool(ProjectToolBase):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="delete_project",
            description=(
                "Delete a project and its entire workspace (tasks and files on disk). "
                "Reference the project by name, slug or id. This cannot be undone."
            ),
            category="projects",
            parameters_schema={
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Project name, slug or id."}
                },
                "required": ["project"],
            },
        )

    async def execute(self, arguments: dict, conversation_id: str) -> ToolResult:
        try:
            async with get_db_session() as db:
                project = await project_service.get_project_by_reference(
                    db, arguments.get("project")
                )
                guard = self._check(project_service.project_root(project))
                if guard:
                    return guard
                name = project.name
                await project_service.delete_project(db, project.id)
        except Exception as exc:
            return self._fail(exc)
        logger.info("delete_project: %s", name)
        return ToolResult(success=True, output={"deleted": name})


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
class ListTasksTool(ProjectToolBase):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="list_tasks",
            description=(
                "List a project's tasks with their id, title, status (todo/doing/done) "
                "and priority. Use the ids when updating, moving or deleting a task."
            ),
            category="projects",
            parameters_schema={
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Project name, slug or id."}
                },
                "required": ["project"],
            },
        )

    async def execute(self, arguments: dict, conversation_id: str) -> ToolResult:
        try:
            async with get_db_session() as db:
                project = await project_service.get_project_by_reference(
                    db, arguments.get("project")
                )
                tasks = await project_service.list_tasks(db, project.id)
                output = {
                    "project": _project_dict(project),
                    "tasks": [_task_dict(t) for t in tasks],
                }
        except Exception as exc:
            return self._fail(exc)
        output["count"] = len(output["tasks"])
        return ToolResult(success=True, output=output)


class CreateTaskTool(ProjectToolBase):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="create_task",
            description=(
                "Add a task to a project's TODO/Kanban board. Reference the project "
                "by name, slug or id. Defaults to the 'todo' column and 'medium' priority."
            ),
            category="projects",
            parameters_schema={
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Project name, slug or id."},
                    "title": {"type": "string", "description": "Task title."},
                    "description": {"type": "string", "description": "Optional task details."},
                    "status": {
                        "type": "string",
                        "enum": ["todo", "doing", "done"],
                        "description": "Kanban column (default: todo).",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "Priority (default: medium).",
                    },
                },
                "required": ["project", "title"],
            },
        )

    async def execute(self, arguments: dict, conversation_id: str) -> ToolResult:
        try:
            async with get_db_session() as db:
                project = await project_service.get_project_by_reference(
                    db, arguments.get("project")
                )
                task = await project_service.create_task(
                    db,
                    project.id,
                    title=arguments.get("title") or "",
                    description=arguments.get("description") or "",
                    status=arguments.get("status") or "todo",
                    priority=arguments.get("priority") or "medium",
                )
                output = _task_dict(task)
        except Exception as exc:
            return self._fail(exc)
        return ToolResult(success=True, output=output)


class UpdateTaskTool(ProjectToolBase):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="update_task",
            description=(
                "Update a task's title, description, status (Kanban column) or "
                "priority. Identify the task to change by its id or title, within a "
                "project referenced by name, slug or id."
            ),
            category="projects",
            parameters_schema={
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Project name, slug or id."},
                    "task": {"type": "string", "description": "Task id or title to update."},
                    "title": {"type": "string", "description": "New title."},
                    "description": {"type": "string", "description": "New description."},
                    "status": {
                        "type": "string",
                        "enum": ["todo", "doing", "done"],
                        "description": "New Kanban column.",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "New priority.",
                    },
                    "position": {"type": "integer", "description": "New order within the column."},
                },
                "required": ["project", "task"],
            },
        )

    async def execute(self, arguments: dict, conversation_id: str) -> ToolResult:
        changes = {
            key: arguments[key]
            for key in ("title", "description", "status", "priority", "position")
            if key in arguments and arguments[key] is not None
        }
        if not changes:
            return ToolResult(success=False, error="No changes were provided.")

        try:
            async with get_db_session() as db:
                project = await project_service.get_project_by_reference(
                    db, arguments.get("project")
                )
                task = await _resolve_task(db, project.id, arguments.get("task") or "")
                task = await project_service.update_task(db, task.id, changes)
                output = _task_dict(task)
        except Exception as exc:
            return self._fail(exc)
        return ToolResult(success=True, output=output)


class MoveTaskTool(ProjectToolBase):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="move_task",
            description=(
                "Move a task to a Kanban column (todo/doing/done), appending it to the "
                "end of that column. Identify the task by id or title within a project."
            ),
            category="projects",
            parameters_schema={
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Project name, slug or id."},
                    "task": {"type": "string", "description": "Task id or title to move."},
                    "status": {
                        "type": "string",
                        "enum": ["todo", "doing", "done"],
                        "description": "Destination Kanban column.",
                    },
                },
                "required": ["project", "task", "status"],
            },
        )

    async def execute(self, arguments: dict, conversation_id: str) -> ToolResult:
        try:
            async with get_db_session() as db:
                project = await project_service.get_project_by_reference(
                    db, arguments.get("project")
                )
                task = await _resolve_task(db, project.id, arguments.get("task") or "")
                task = await project_service.move_task(
                    db, project.id, task.id, arguments.get("status") or "todo"
                )
                output = _task_dict(task)
        except Exception as exc:
            return self._fail(exc)
        return ToolResult(success=True, output=output)


class DeleteTaskTool(ProjectToolBase):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="delete_task",
            description=(
                "Delete a task from a project. Identify it by id or title within a "
                "project referenced by name, slug or id."
            ),
            category="projects",
            parameters_schema={
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Project name, slug or id."},
                    "task": {"type": "string", "description": "Task id or title to delete."},
                },
                "required": ["project", "task"],
            },
        )

    async def execute(self, arguments: dict, conversation_id: str) -> ToolResult:
        try:
            async with get_db_session() as db:
                project = await project_service.get_project_by_reference(
                    db, arguments.get("project")
                )
                task = await _resolve_task(db, project.id, arguments.get("task") or "")
                title = task.title
                await project_service.delete_task(db, task.id)
        except Exception as exc:
            return self._fail(exc)
        return ToolResult(success=True, output={"deleted": title})


# ---------------------------------------------------------------------------
# Project files (the on-disk workspace)
# ---------------------------------------------------------------------------
class ListProjectFilesTool(ProjectToolBase):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="list_project_files",
            description=(
                "List files and folders inside a project's workspace. Optionally pass "
                "a relative `path` to list a subfolder."
            ),
            category="projects",
            parameters_schema={
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Project name, slug or id."},
                    "path": {
                        "type": "string",
                        "description": "Relative folder inside the workspace (default: root).",
                    },
                },
                "required": ["project"],
            },
        )

    async def execute(self, arguments: dict, conversation_id: str) -> ToolResult:
        try:
            async with get_db_session() as db:
                project = await project_service.get_project_by_reference(
                    db, arguments.get("project")
                )
                listing = await project_service.list_dir(
                    db, project, arguments.get("path") or ""
                )
                output = {
                    "path": listing.path,
                    "entries": [_file_dict(e) for e in listing.entries],
                }
        except Exception as exc:
            return self._fail(exc)
        return ToolResult(success=True, output=output)


class ReadProjectFileTool(ProjectToolBase):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_project_file",
            description=(
                "Read a text file from a project's workspace (relative path). Binary "
                "or very large files are rejected."
            ),
            category="projects",
            parameters_schema={
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Project name, slug or id."},
                    "path": {"type": "string", "description": "Relative file path."},
                },
                "required": ["project", "path"],
            },
        )

    async def execute(self, arguments: dict, conversation_id: str) -> ToolResult:
        try:
            async with get_db_session() as db:
                project = await project_service.get_project_by_reference(
                    db, arguments.get("project")
                )
                content = project_service.read_text(project, arguments.get("path") or "")
                output = {"path": arguments.get("path"), "content": content}
        except Exception as exc:
            return self._fail(exc)
        return ToolResult(success=True, output=output)


class WriteProjectFileTool(ProjectToolBase):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="write_project_file",
            description=(
                "Create or overwrite a text file in a project's workspace (relative "
                "path). Parent folders are created automatically."
            ),
            category="projects",
            parameters_schema={
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Project name, slug or id."},
                    "path": {"type": "string", "description": "Relative file path."},
                    "content": {"type": "string", "description": "Text content to write."},
                },
                "required": ["project", "path", "content"],
            },
        )

    async def execute(self, arguments: dict, conversation_id: str) -> ToolResult:
        try:
            async with get_db_session() as db:
                project = await project_service.get_project_by_reference(
                    db, arguments.get("project")
                )
                guard = self._check(project_service.project_root(project))
                if guard:
                    return guard
                entry = project_service.write_text(
                    project,
                    arguments.get("path") or "",
                    arguments.get("content") or "",
                )
                output = _file_dict(entry)
        except Exception as exc:
            return self._fail(exc)
        return ToolResult(success=True, output=output)


class CreateProjectDirectoryTool(ProjectToolBase):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="create_project_directory",
            description="Create a folder inside a project's workspace (relative path).",
            category="projects",
            parameters_schema={
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Project name, slug or id."},
                    "path": {"type": "string", "description": "Relative folder path."},
                },
                "required": ["project", "path"],
            },
        )

    async def execute(self, arguments: dict, conversation_id: str) -> ToolResult:
        try:
            async with get_db_session() as db:
                project = await project_service.get_project_by_reference(
                    db, arguments.get("project")
                )
                guard = self._check(project_service.project_root(project))
                if guard:
                    return guard
                entry = project_service.make_directory(project, arguments.get("path") or "")
                output = _file_dict(entry)
        except Exception as exc:
            return self._fail(exc)
        return ToolResult(success=True, output=output)


class DeleteProjectFileTool(ProjectToolBase):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="delete_project_file",
            description=(
                "Delete a file or folder (recursively) from a project's workspace "
                "(relative path)."
            ),
            category="projects",
            parameters_schema={
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Project name, slug or id."},
                    "path": {"type": "string", "description": "Relative path to delete."},
                },
                "required": ["project", "path"],
            },
        )

    async def execute(self, arguments: dict, conversation_id: str) -> ToolResult:
        try:
            async with get_db_session() as db:
                project = await project_service.get_project_by_reference(
                    db, arguments.get("project")
                )
                guard = self._check(project_service.project_root(project))
                if guard:
                    return guard
                path = arguments.get("path") or ""
                project_service.delete_path(project, path)
        except Exception as exc:
            return self._fail(exc)
        return ToolResult(success=True, output={"deleted": path})


def create_project_tools(security: SecurityPolicy) -> list:
    """Factory for all project management tools."""
    return [
        ListProjectsTool(security),
        GetProjectTool(security),
        CreateProjectTool(security),
        UpdateProjectTool(security),
        DeleteProjectTool(security),
        ListTasksTool(security),
        CreateTaskTool(security),
        UpdateTaskTool(security),
        MoveTaskTool(security),
        DeleteTaskTool(security),
        ListProjectFilesTool(security),
        ReadProjectFileTool(security),
        WriteProjectFileTool(security),
        CreateProjectDirectoryTool(security),
        DeleteProjectFileTool(security),
    ]
