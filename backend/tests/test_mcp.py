"""MCP integration tests.

Everything here runs against a **fake** MCP session: no SDK, no child process
and no network. The tests cover parsing the server config, tool discovery and
lifecycle, the adapter -> ``LLMTool``/``BaseTool`` mapping, result conversion
and — most importantly — the security gate: an untrusted server's tool must
trigger a `permission_request`, while a trusted one runs directly (but still
respects the workspace boundary for path arguments).
"""
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import app.config as config_module
from app.agent.mcp.config import McpServerConfig, parse_mcp_servers
from app.agent.mcp.manager import MCPManager
from app.agent.mcp.tool import McpToolAdapter, McpToolInfo, create_mcp_tools
from app.security.path_guard import PathGuard
from app.security.permissions import permission_manager
from app.security.policy import SecurityPolicy
from app.tools.base import BaseTool


# ---------------------------------------------------------------------------
# Fake MCP surface
# ---------------------------------------------------------------------------
class FakeTool:
    def __init__(self, name, description="", input_schema=None, read_only=False):
        self.name = name
        self.description = description
        self.input_schema = input_schema or {"type": "object", "properties": {}}
        self.annotations = SimpleNamespace(read_only_hint=read_only)


class FakeText:
    type = "text"

    def __init__(self, text):
        self.text = text


class FakeCallToolResult:
    def __init__(self, content=None, structured_content=None, is_error=False):
        self.content = content if content is not None else []
        self.structured_content = structured_content
        self.is_error = is_error


class FakeSession:
    def __init__(self, tools, call_results=None, call_error=None):
        self._tools = tools
        self._call_results = call_results or {}
        self._call_error = call_error
        self.initialized = False
        self.calls: list[tuple] = []

    async def initialize(self):
        self.initialized = True
        return SimpleNamespace()

    async def list_tools(self):
        return SimpleNamespace(tools=list(self._tools))

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if self._call_error is not None:
            raise self._call_error
        return self._call_results.get(
            name, FakeCallToolResult(content=[FakeText("ok")])
        )


def make_session_factory(session, fail=False):
    @asynccontextmanager
    async def factory(_config):
        if fail:
            raise RuntimeError("could not start server")
        yield session

    return factory


class FakeWSManager:
    def __init__(self):
        self.broadcasts: list[tuple[str, dict]] = []

    async def broadcast_to_conversation(self, conversation_id, data):
        self.broadcasts.append((conversation_id, data))

    def permission_requests(self):
        return [d for _, d in self.broadcasts if d.get("type") == "permission_request"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
async def mcp_db(tmp_path, monkeypatch):
    """Point the shared DB session factory at a throwaway SQLite file."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.database import session as session_module
    from app.database.models import Base

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'mcp.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    # ``get_db_session`` looks up the module global at call time, so patching it
    # here redirects the adapter's permission rows to the temp DB.
    monkeypatch.setattr(session_module, "AsyncSessionLocal", factory)
    yield factory
    await engine.dispose()


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    ws = tmp_path / "workspace"
    ws.mkdir()
    monkeypatch.setattr(config_module.settings, "odin_workspace", str(ws))
    return ws


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------
class TestParseConfig:
    def test_empty(self):
        assert parse_mcp_servers("") == []
        assert parse_mcp_servers("   ") == []

    def test_valid_stdio_and_remote(self):
        raw = (
            '[{"name":"fs","command":"npx","args":["-y","srv","/tmp"]},'
            ' {"name":"net","transport":"sse","url":"http://x/sse","trusted":true}]'
        )
        servers = parse_mcp_servers(raw)
        assert [s.name for s in servers] == ["fs", "net"]
        assert servers[0].transport == "stdio"
        assert servers[0].args == ["-y", "srv", "/tmp"]
        assert servers[1].trusted is True
        assert servers[1].target() == "http://x/sse"

    def test_mapping_shape(self):
        servers = parse_mcp_servers('{"fs":{"command":"npx"}}')
        assert len(servers) == 1 and servers[0].name == "fs"

    def test_invalid_json_is_ignored(self):
        assert parse_mcp_servers("{not json") == []

    def test_bad_entries_are_skipped(self):
        raw = (
            '[{"name":"ok","command":"x"},'
            ' {"name":"no-command"},'
            ' {"name":"bad-remote","transport":"sse"}]'
        )
        assert [s.name for s in parse_mcp_servers(raw)] == ["ok"]

    def test_duplicates_are_skipped(self):
        raw = '[{"name":"a","command":"x"},{"name":"a","command":"y"}]'
        assert len(parse_mcp_servers(raw)) == 1


# ---------------------------------------------------------------------------
# Manager lifecycle & discovery
# ---------------------------------------------------------------------------
class TestManager:
    async def test_no_servers_is_a_noop(self):
        manager = MCPManager(session_factory=make_session_factory(FakeSession([])))
        await manager.start(configs=[])
        assert manager.status() == []
        assert manager.tool_count() == 0

    async def test_discovers_tools_and_status(self):
        tools = [
            FakeTool("read_file", "Read a file", read_only=True),
            FakeTool("write_file", "Write a file"),
        ]
        session = FakeSession(tools)
        manager = MCPManager(session_factory=make_session_factory(session))
        cfg = McpServerConfig(name="filesystem", command="fake")
        await manager.start(configs=[cfg], startup_timeout=1)
        try:
            assert session.initialized is True
            assert manager.tool_count() == 2
            status = manager.status()[0]
            assert status["name"] == "filesystem"
            assert status["status"] == "connected"
            assert status["tool_count"] == 2
            assert status["trusted"] is False
            assert status["transport"] == "stdio"
        finally:
            await manager.stop()

    async def test_connection_failure_is_reported_not_raised(self):
        manager = MCPManager(session_factory=make_session_factory(None, fail=True))
        cfg = McpServerConfig(name="broker", command="nope")
        await manager.start(configs=[cfg], startup_timeout=1)
        status = manager.status()[0]
        assert status["status"] == "error"
        assert "could not start server" in status["error"]
        await manager.stop()

    async def test_call_tool_routes_to_server(self):
        session = FakeSession(
            [FakeTool("echo")],
            call_results={"echo": FakeCallToolResult(content=[FakeText("hi")])},
        )
        manager = MCPManager(session_factory=make_session_factory(session))
        cfg = McpServerConfig(name="fs", command="fake")
        await manager.start(configs=[cfg], startup_timeout=1)
        try:
            result = await manager.call_tool("fs", "echo", {"value": 1})
            assert session.calls == [("echo", {"value": 1})]
            assert result.content[0].text == "hi"
        finally:
            await manager.stop()

    async def test_unknown_server_raises(self):
        manager = MCPManager(session_factory=make_session_factory(FakeSession([])))
        with pytest.raises(RuntimeError, match="Unknown MCP server"):
            await manager.call_tool("missing", "t", {})

    async def test_create_mcp_tools_from_manager(self):
        session = FakeSession([FakeTool("a"), FakeTool("b")])
        manager = MCPManager(session_factory=make_session_factory(session))
        cfg = McpServerConfig(name="filesystem", command="fake")
        await manager.start(configs=[cfg], startup_timeout=1)
        try:
            adapters = create_mcp_tools(manager, SecurityPolicy(PathGuard()))
            assert [a.definition.name for a in adapters] == [
                "mcp__filesystem__a",
                "mcp__filesystem__b",
            ]
        finally:
            await manager.stop()


# ---------------------------------------------------------------------------
# Adapter mapping
# ---------------------------------------------------------------------------
class TestAdapter:
    def test_implements_base_tool_and_namespacing(self):
        info = McpToolInfo(
            server="file system!",
            trusted=False,
            name="read/file",
            description="Read a file",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            read_only=True,
        )
        adapter = McpToolAdapter(manager=None, info=info, security_policy=None)
        assert isinstance(adapter, BaseTool)
        d = adapter.definition
        assert d.name == "mcp__file_system__read_file"
        assert d.category == "mcp"
        assert d.requires_approval_by_default is True
        assert d.parameters_schema["properties"]["path"]["type"] == "string"

    def test_trusted_definition_does_not_require_approval_by_default(self):
        info = McpToolInfo("fs", True, "read", "", {}, read_only=True)
        adapter = McpToolAdapter(manager=None, info=info, security_policy=None)
        assert adapter.definition.requires_approval_by_default is False


# ---------------------------------------------------------------------------
# Result conversion
# ---------------------------------------------------------------------------
class TestResultConversion:
    async def _call_with_result(self, result, read_only=False):
        session = FakeSession(
            [FakeTool("t", read_only=read_only)], call_results={"t": result}
        )
        manager = MCPManager(session_factory=make_session_factory(session))
        cfg = McpServerConfig(name="fs", command="fake", trusted=True)
        await manager.start(configs=[cfg], startup_timeout=1)
        try:
            info = McpToolInfo("fs", True, "t", "", {}, read_only=read_only)
            adapter = McpToolAdapter(manager, info, SecurityPolicy(PathGuard()))
            return await adapter.execute({}, "conv")
        finally:
            await manager.stop()

    async def test_text_result(self):
        result = await self._call_with_result(
            FakeCallToolResult(content=[FakeText("hello")])
        )
        assert result.success is True
        assert result.output == "hello"

    async def test_structured_result(self):
        result = await self._call_with_result(
            FakeCallToolResult(structured_content={"answer": 42})
        )
        assert result.output == {"answer": 42}

    async def test_error_result(self):
        result = await self._call_with_result(
            FakeCallToolResult(content=[FakeText("boom")], is_error=True)
        )
        assert result.success is False
        assert result.error == "boom"

    async def test_transport_error_becomes_failure(self):
        session = FakeSession([FakeTool("t")], call_error=RuntimeError("gone"))
        manager = MCPManager(session_factory=make_session_factory(session))
        cfg = McpServerConfig(name="fs", command="fake", trusted=True)
        await manager.start(configs=[cfg], startup_timeout=1)
        try:
            info = McpToolInfo("fs", True, "t", "", {}, read_only=False)
            adapter = McpToolAdapter(manager, info, SecurityPolicy(PathGuard()))
            result = await adapter.execute({}, "conv")
            assert result.success is False
            assert "gone" in result.error
        finally:
            await manager.stop()


# ---------------------------------------------------------------------------
# Security gate — the heart of this phase
# ---------------------------------------------------------------------------
class TestSecurityGate:
    async def _adapter(self, read_only, trusted, policy, ws_manager, call_result=None):
        session = FakeSession(
            [FakeTool("do", read_only=read_only)],
            call_results={
                "do": call_result or FakeCallToolResult(content=[FakeText("done")])
            },
        )
        manager = MCPManager(session_factory=make_session_factory(session))
        cfg = McpServerConfig(name="srv", command="fake", trusted=trusted)
        await manager.start(configs=[cfg], startup_timeout=1)
        info = McpToolInfo("srv", trusted, "do", "", {}, read_only=read_only)
        adapter = McpToolAdapter(manager, info, policy, ws_manager)
        return manager, adapter, session

    async def test_untrusted_tool_requests_permission(
        self, mcp_db, workspace, monkeypatch
    ):
        policy = SecurityPolicy(PathGuard())
        ws = FakeWSManager()
        requests = []

        async def fake_approval(request_id):
            requests.append(request_id)
            return True

        monkeypatch.setattr(permission_manager, "request_approval", fake_approval)

        manager, adapter, session = await self._adapter(False, False, policy, ws)
        try:
            result = await adapter.execute({"value": 1}, "conv-1")
        finally:
            await manager.stop()

        assert result.success is True
        assert requests, "request_approval should have been called"
        assert ws.permission_requests(), "a permission_request event should be broadcast"
        event = ws.permission_requests()[0]
        assert event["tool"] == "mcp__srv__do"
        assert event["operation"] == "EXECUTE"
        assert event["id"] == requests[0]

        from sqlalchemy import select

        from app.database.models import PermissionRequest

        async with mcp_db() as db:
            rows = (await db.execute(select(PermissionRequest))).scalars().all()
        assert len(rows) == 1
        assert rows[0].tool == "mcp__srv__do"
        assert rows[0].status == "approved"
        assert session.calls == [("do", {"value": 1})]

    async def test_untrusted_denied_does_not_execute(
        self, mcp_db, workspace, monkeypatch
    ):
        policy = SecurityPolicy(PathGuard())

        async def deny(_request_id):
            return False

        monkeypatch.setattr(permission_manager, "request_approval", deny)

        manager, adapter, session = await self._adapter(False, False, policy, None)
        try:
            result = await adapter.execute({}, "conv-2")
        finally:
            await manager.stop()

        assert result.success is False
        assert result.requires_approval is True
        assert result.permission_request_id
        assert session.calls == []

    async def test_trusted_tool_runs_directly(self, mcp_db, workspace, monkeypatch):
        policy = SecurityPolicy(PathGuard())
        ws = FakeWSManager()

        async def should_not_be_called(_request_id):  # pragma: no cover
            raise AssertionError("trusted tool must not ask for approval")

        monkeypatch.setattr(permission_manager, "request_approval", should_not_be_called)

        manager, adapter, session = await self._adapter(False, True, policy, ws)
        try:
            result = await adapter.execute({}, "conv-3")
        finally:
            await manager.stop()

        assert result.success is True
        assert ws.permission_requests() == []
        assert session.calls == [("do", {})]

    async def test_trusted_write_outside_workspace_requires_approval(
        self, mcp_db, workspace, monkeypatch
    ):
        policy = SecurityPolicy(PathGuard())
        ws = FakeWSManager()
        seen = []

        async def capture(request_id):
            seen.append(request_id)
            return True

        monkeypatch.setattr(permission_manager, "request_approval", capture)

        manager, adapter, session = await self._adapter(False, True, policy, ws)
        try:
            result = await adapter.execute({"path": "/etc/odin.conf"}, "conv-4")
        finally:
            await manager.stop()

        assert result.success is True
        assert seen, "writing outside the workspace should require approval"
        # The event reports the tool's own intent (EXECUTE); the path check is
        # what made the decision REQUIRE_APPROVAL.
        assert ws.permission_requests()[0]["operation"] == "EXECUTE"

    async def test_trusted_read_of_blocked_path_is_denied(
        self, mcp_db, workspace, monkeypatch
    ):
        policy = SecurityPolicy(PathGuard())

        async def never(_request_id):  # pragma: no cover
            raise AssertionError("a DENY must not reach the approval flow")

        monkeypatch.setattr(permission_manager, "request_approval", never)

        manager, adapter, session = await self._adapter(True, True, policy, None)
        try:
            result = await adapter.execute({"path": "/proc/self/status"}, "conv-5")
        finally:
            await manager.stop()

        assert result.success is False
        assert "Access denied" in result.error
        assert session.calls == []

    async def test_trusted_in_workspace_path_allowed(
        self, mcp_db, workspace, monkeypatch
    ):
        policy = SecurityPolicy(PathGuard())

        async def never(_request_id):  # pragma: no cover
            raise AssertionError("workspace paths must not require approval")

        monkeypatch.setattr(permission_manager, "request_approval", never)

        manager, adapter, session = await self._adapter(False, True, policy, None)
        target = str(workspace / "notes.txt")
        try:
            result = await adapter.execute({"path": target}, "conv-6")
        finally:
            await manager.stop()

        assert result.success is True
        assert session.calls == [("do", {"path": target})]
