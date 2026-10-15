"""Connection manager for MCP servers.

Each configured server gets one long-lived asyncio task that owns its transport
and ``ClientSession`` for the whole process lifetime. Keeping the (anyio-based)
context managers inside a single task is what makes this work: opening them in
one task and closing them in another raises "Attempted to exit cancel scope in
a different task". Tool calls are funnelled to that task through a queue.

The ``mcp`` SDK is imported lazily and only when servers are configured, so the
package stays optional — with no servers (or no SDK) Odin boots exactly as
before.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable

from app.agent.mcp.config import McpServerConfig, parse_mcp_servers
from app.agent.mcp.tool import McpToolInfo
from app.config import settings

logger = logging.getLogger("odin.agent.mcp.manager")

# A session factory is an async context manager yielding an object exposing
# ``initialize()``, ``list_tools()`` and ``call_tool()`` — i.e. the subset of
# ``mcp.ClientSession`` this manager uses. Tests inject a fake.
SessionFactory = Callable[[McpServerConfig], AsyncIterator[Any]]


@asynccontextmanager
async def default_session_factory(config: McpServerConfig) -> AsyncIterator[Any]:
    """Open a real MCP session with the (lazily imported) ``mcp`` SDK."""
    if config.transport == "stdio":
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=config.command,
            args=list(config.args or []),
            env=config.env or None,
            cwd=config.cwd,
        )
        transport = stdio_client(params)
    elif config.transport == "sse":
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        transport = sse_client(config.url, headers=config.headers or None)
    elif config.transport == "http":
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        transport = streamable_http_client(config.url)
    else:  # pragma: no cover - guarded by config validation
        raise ValueError(f"Unsupported MCP transport: {config.transport}")

    async with transport as streams:
        read, write = streams[0], streams[1]
        async with ClientSession(read, write) as session:
            yield session


class MCPServerConnection:
    """One MCP server: its worker task, connection state and tools."""

    def __init__(
        self,
        config: McpServerConfig,
        session_factory: SessionFactory,
    ) -> None:
        self.config = config
        self.name = config.name
        self.trusted = config.trusted
        self.status = "disconnected"  # disconnected | connected | error
        self.error: str | None = None
        self.tools: list[Any] = []
        self._factory = session_factory
        self._task: asyncio.Task | None = None
        self._ready = asyncio.Event()
        self._requests: asyncio.Queue = asyncio.Queue()

    # -- lifecycle ------------------------------------------------------
    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name=f"mcp-{self.name}")

    async def _run(self) -> None:
        try:
            async with self._factory(self.config) as session:
                await session.initialize()
                result = await session.list_tools()
                self.tools = list(getattr(result, "tools", None) or [])
                self.status = "connected"
                self._ready.set()
                logger.info(
                    "MCP server %r connected (%d tools)", self.name, len(self.tools)
                )
                await self._serve(session)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.status = "error"
            self.error = str(exc)
            logger.warning("MCP server %r failed to connect: %s", self.name, exc)
        finally:
            self._ready.set()
            if self.status == "connected":
                self.status = "disconnected"

    async def _serve(self, session: Any) -> None:
        """Serve tool calls on this task until asked to stop."""
        while True:
            item = await self._requests.get()
            if item is None:  # stop sentinel
                return
            name, arguments, future = item
            try:
                result = await session.call_tool(name, arguments)
                if not future.done():
                    future.set_result(result)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if not future.done():
                    future.set_exception(exc)

    async def wait_ready(self, timeout: float) -> None:
        if self._ready.is_set():
            return
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            if self.status == "disconnected":
                self.status = "error"
                self.error = f"Timed out after {timeout:.0f}s while connecting"
                self._ready.set()

    async def stop(self) -> None:
        if self._task is None:
            return
        self._requests.put_nowait(None)
        try:
            await asyncio.wait_for(self._task, timeout=3)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        except Exception:
            pass
        self._task = None

    # -- calls ----------------------------------------------------------
    async def call_tool(self, name: str, arguments: dict) -> Any:
        if self.status != "connected":
            raise RuntimeError(f"MCP server '{self.name}' is not connected")
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        await self._requests.put((name, arguments, future))
        return await future

    # -- introspection --------------------------------------------------
    def status_dict(self) -> dict:
        detail = f"MCP server ({self.config.transport})"
        if self.trusted:
            detail += " · trusted"
        return {
            "name": self.name,
            "description": detail,
            "status": self.status,
            "tool_count": len(self.tools),
            "url": self.config.target() or None,
            "transport": self.config.transport,
            "trusted": self.trusted,
            "error": self.error,
        }


class MCPManager:
    """Owns every configured MCP connection for the process."""

    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self._session_factory = session_factory or default_session_factory
        self._connections: dict[str, MCPServerConnection] = {}
        self._started = False

    async def start(
        self,
        configs: list[McpServerConfig] | None = None,
        startup_timeout: float | None = None,
    ) -> None:
        if self._started:
            return
        self._started = True

        configs = (
            configs if configs is not None else parse_mcp_servers(settings.odin_mcp_servers)
        )
        if not configs:
            logger.info("No MCP servers configured")
            return

        # The SDK is optional: if a server is configured but `mcp` is missing,
        # log and carry on rather than breaking startup.
        if self._session_factory is default_session_factory:
            try:
                import mcp  # noqa: F401
            except ImportError:
                logger.warning(
                    "MCP servers are configured but the 'mcp' package is not "
                    "installed; skipping MCP tools. Install it with "
                    "`pip install -r requirements.txt`."
                )
                return

        timeout = (
            startup_timeout
            if startup_timeout is not None
            else settings.odin_mcp_startup_timeout
        )
        self._connections = {
            cfg.name: MCPServerConnection(cfg, self._session_factory) for cfg in configs
        }
        for connection in self._connections.values():
            connection.start()

        await asyncio.gather(
            *(c.wait_ready(timeout) for c in self._connections.values())
        )
        connected = sum(1 for c in self._connections.values() if c.status == "connected")
        logger.info(
            "MCP: %d/%d servers connected, %d tools discovered",
            connected,
            len(self._connections),
            self.tool_count(),
        )

    async def stop(self) -> None:
        await asyncio.gather(
            *(c.stop() for c in self._connections.values()), return_exceptions=True
        )
        self._connections.clear()
        self._started = False

    def get_connection(self, name: str) -> MCPServerConnection | None:
        return self._connections.get(name)

    def tool_count(self) -> int:
        return sum(len(c.tools) for c in self._connections.values())

    def iter_tool_infos(self) -> list[McpToolInfo]:
        infos: list[McpToolInfo] = []
        for connection in self._connections.values():
            if connection.status != "connected":
                continue
            for tool in connection.tools:
                infos.append(
                    McpToolInfo.from_tool(connection.name, connection.trusted, tool)
                )
        return infos

    async def call_tool(self, server: str, tool: str, arguments: dict) -> Any:
        connection = self._connections.get(server)
        if connection is None:
            raise RuntimeError(f"Unknown MCP server: {server}")
        return await connection.call_tool(tool, arguments)

    def status(self) -> list[dict]:
        return [c.status_dict() for c in self._connections.values()]


# Singleton shared across the application (registered in main.py lifespan).
mcp_manager = MCPManager()
