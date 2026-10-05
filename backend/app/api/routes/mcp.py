from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class MCPServer(BaseModel):
    name: str
    description: str
    status: str  # connected | disconnected | error
    tool_count: int
    url: str | None = None


# Mocked MCP servers - no real MCP implemented in MVP
MOCK_MCP_SERVERS: list[MCPServer] = [
    MCPServer(
        name="Filesystem",
        description="Access local filesystem via MCP protocol",
        status="disconnected",
        tool_count=0,
        url="mcp://filesystem",
    ),
    MCPServer(
        name="GitHub",
        description="GitHub repository management",
        status="disconnected",
        tool_count=0,
        url="mcp://github",
    ),
    MCPServer(
        name="Browser",
        description="Web browsing and scraping",
        status="disconnected",
        tool_count=0,
        url="mcp://browser",
    ),
    MCPServer(
        name="Database",
        description="Database query and management",
        status="disconnected",
        tool_count=0,
        url="mcp://database",
    ),
]


@router.get("", response_model=list[MCPServer])
async def list_mcp_servers():
    """Returns mocked MCP server list. Real MCP not implemented in MVP."""
    return MOCK_MCP_SERVERS
