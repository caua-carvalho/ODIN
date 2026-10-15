"""Real status of the configured MCP servers.

The servers and their tools are managed by :mod:`app.agent.mcp.manager`, which
is populated during the startup lifespan. With no servers configured the list
is simply empty (no mock data).
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class MCPServer(BaseModel):
    name: str
    description: str
    status: str  # connected | disconnected | error
    tool_count: int
    # Kept for the existing panel contract (frontend/src/types/mcp.ts).
    url: str | None = None
    # Additive fields with live details.
    transport: str | None = None
    trusted: bool = False
    error: str | None = None


@router.get("", response_model=list[MCPServer])
async def list_mcp_servers():
    """Live status of the configured MCP servers and their discovered tools."""
    from app.agent.mcp.manager import mcp_manager

    return [MCPServer(**entry) for entry in mcp_manager.status()]
