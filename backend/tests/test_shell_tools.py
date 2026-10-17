"""Safe timeout/cancellation tests for the shell tool (issue #19).

``execute_command`` must not leave orphaned descendants behind when a command
hits its timeout or when the turn is cancelled (a user "stop"). The command
used below spawns a real background child (``sleep 300 &``) and records its pid,
so the assertions can prove the whole process group is gone.

Everything is offline and hermetic: no network, no database and no LLM. The
permission gate is stubbed out so the test never blocks on HITL approval.
"""
import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("GEMINI_API_KEY", "test-key")

from app.security.path_guard import PathGuard
from app.security.policy import SecurityPolicy
from app.tools.shell.tools import ExecuteCommandTool

# Spawns a 5-minute background child, records its pid, then ``wait``s so the
# parent shell stays alive (the timeout/cancellation targets the whole group).
_SPAWN_CHILD = "bash -c 'sleep 300 & echo $! > child.pid; wait'"


def _make_tool(tmp_path, monkeypatch) -> ExecuteCommandTool:
    guard = PathGuard()
    guard.workspace = tmp_path
    policy = SecurityPolicy(guard)

    async def _approve(self, **kwargs):  # noqa: ANN001 - match tool signature
        return True, "test-request"

    monkeypatch.setattr(ExecuteCommandTool, "_request_permission", _approve)
    return ExecuteCommandTool(policy, guard)


def _alive(pid: int) -> bool:
    """True while ``pid`` exists (zombies still count as existing)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # pragma: no cover - not our process
        return True
    return True


async def _wait_until_dead(pid: int, timeout: float = 5.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if not _alive(pid):
            return True
        await asyncio.sleep(0.05)
    return not _alive(pid)


async def _read_child_pid(path: Path, timeout: float = 5.0) -> int:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if path.exists():
            text = path.read_text().strip()
            if text:
                return int(text)
        await asyncio.sleep(0.05)
    raise AssertionError(f"child pid file never appeared: {path}")


async def test_timeout_kills_background_child(tmp_path, monkeypatch):
    """A command that exceeds its timeout leaves no descendant alive."""
    tool = _make_tool(tmp_path, monkeypatch)

    result = await tool.execute(
        {"command": _SPAWN_CHILD, "timeout": 1},
        "conv-timeout",
    )

    assert result.success is False
    assert result.error == f"Command timed out after 1s: {_SPAWN_CHILD}"

    child_pid = await _read_child_pid(tmp_path / "child.pid")
    assert await _wait_until_dead(child_pid), f"orphaned child survived: {child_pid}"


async def test_cancellation_kills_background_child(tmp_path, monkeypatch):
    """Cancelling the turn (user stop) must kill the whole process group."""
    tool = _make_tool(tmp_path, monkeypatch)

    task = asyncio.create_task(
        tool.execute(
            {"command": _SPAWN_CHILD, "timeout": 30},
            "conv-cancel",
        )
    )

    try:
        child_pid = await _read_child_pid(tmp_path / "child.pid")
        assert _alive(child_pid)  # sanity: the child really is running

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert await _wait_until_dead(
            child_pid
        ), f"orphaned child survived cancellation: {child_pid}"
    finally:
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task


async def test_successful_command_reports_exit_code(tmp_path, monkeypatch):
    """The happy path still returns the normal ToolResult contract."""
    tool = _make_tool(tmp_path, monkeypatch)

    result = await tool.execute(
        {"command": "echo hello", "timeout": 5},
        "conv-ok",
    )

    assert result.success is True
    assert result.output["exit_code"] == 0
    assert result.output["stdout"].strip() == "hello"
