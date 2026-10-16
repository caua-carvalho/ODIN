"""Parsing and validation of the ``ODIN_MCP_SERVERS`` configuration.

The setting is a JSON array so the format is self-describing and can express
both command-based (``stdio``) and URL-based (``sse``/``http``) servers::

    [
      {
        "name": "filesystem",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        "trusted": false
      },
      {
        "name": "remote",
        "transport": "sse",
        "url": "http://localhost:3001/sse",
        "trusted": true
      }
    ]

Parsing is deliberately tolerant: a malformed ``ODIN_MCP_SERVERS`` (or a single
bad entry) is logged and skipped so a configuration mistake can never stop the
backend from booting.
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger("odin.agent.mcp.config")


class McpServerConfig(BaseModel):
    """A single configured MCP server."""

    name: str
    transport: Literal["stdio", "sse", "http"] = "stdio"

    # stdio transport
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    cwd: str | None = None

    # remote transports (sse / http)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)

    # Security: a trusted server's tools skip the blanket approval that every
    # other MCP tool requires. See app/agent/mcp/tool.py.
    trusted: bool = False

    def target(self) -> str:
        """Human-readable connection target, shown in ``/api/mcp``."""
        if self.transport == "stdio":
            return " ".join([self.command or ""] + list(self.args)).strip()
        return self.url or ""

    def validate_for_transport(self) -> None:
        if not self.name.strip():
            raise ValueError("server 'name' must not be empty")
        if self.transport == "stdio" and not (self.command or "").strip():
            raise ValueError("stdio server requires a 'command'")
        if self.transport in ("sse", "http") and not (self.url or "").strip():
            raise ValueError(f"{self.transport} server requires a 'url'")


def _coerce_list(raw: object) -> list[dict]:
    """Accept a few convenient shapes and always return a list of dicts.

    Supports a JSON list of objects, ``{"servers": [...]}``, and a mapping of
    ``{name: {..server fields..}}``.
    """
    if isinstance(raw, dict):
        servers = raw.get("servers", raw)
        if isinstance(servers, dict):
            return [
                {"name": name, **value}
                for name, value in servers.items()
                if isinstance(value, dict)
            ]
        return servers if isinstance(servers, list) else []
    return raw if isinstance(raw, list) else []


def parse_mcp_servers(raw: str) -> list[McpServerConfig]:
    """Parse the raw setting into validated server configs (best-effort)."""
    raw = (raw or "").strip()
    if not raw:
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("ODIN_MCP_SERVERS is not valid JSON, ignoring it: %s", exc)
        return []

    entries = _coerce_list(data)
    if not entries and data not in ([], {}, None):
        logger.error("ODIN_MCP_SERVERS must be a JSON list of server objects")
        return []

    servers: list[McpServerConfig] = []
    seen: set[str] = set()
    for entry in entries:
        try:
            server = McpServerConfig.model_validate(entry)
            server.validate_for_transport()
        except (ValidationError, ValueError) as exc:
            logger.error("Skipping invalid MCP server entry %r: %s", entry, exc)
            continue
        if server.name in seen:
            logger.warning("Skipping duplicate MCP server name %r", server.name)
            continue
        seen.add(server.name)
        servers.append(server)
    return servers
