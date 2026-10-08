import logging
import logging.config
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database.session import init_db
from app.agent.agent import OdinAgent
from app.agent.providers import create_llm_provider
from app.tools.registry import ToolRegistry
from app.tools.filesystem.tools import create_filesystem_tools
from app.tools.shell.tools import ExecuteCommandTool
from app.security.path_guard import PathGuard
from app.security.policy import SecurityPolicy
from app.api.websocket import ws_manager

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("odin.main")

# Global singletons (initialized in lifespan)
tool_registry: ToolRegistry = ToolRegistry()
odin_agent: OdinAgent | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    global odin_agent

    logger.info("Starting Odin...")

    # Ensure workspace exists
    workspace_path = Path(settings.odin_workspace)
    workspace_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Workspace: {workspace_path}")

    # Init database
    await init_db()
    logger.info("Database initialized")

    # Initialize security
    path_guard = PathGuard()
    security_policy = SecurityPolicy(path_guard)

    # Register tools
    for fs_tool in create_filesystem_tools(security_policy, path_guard, ws_manager):
        tool_registry.register(fs_tool)

    shell_tool = ExecuteCommandTool(security_policy, path_guard, ws_manager)
    tool_registry.register(shell_tool)

    logger.info(f"Registered {len(tool_registry)} tools: {tool_registry.names()}")

    # Initialize LLM provider (selection lives in providers/factory.py)
    provider = create_llm_provider(settings)

    # Initialize agent
    odin_agent = OdinAgent(
        provider=provider,
        tool_registry=tool_registry,
        websocket_manager=ws_manager,
    )
    logger.info("Odin agent ready")

    yield

    logger.info("Odin shutting down...")


app = FastAPI(
    title="Odin",
    description="Personal AI Assistant",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
from app.api.routes import conversations, tools, skills, permissions, mcp, system, chat

app.include_router(conversations.router, prefix="/api/conversations", tags=["conversations"])
app.include_router(tools.router, prefix="/api/tools", tags=["tools"])
app.include_router(skills.router, prefix="/api/skills", tags=["skills"])
app.include_router(permissions.router, prefix="/api/permissions", tags=["permissions"])
app.include_router(mcp.router, prefix="/api/mcp", tags=["mcp"])
app.include_router(system.router, prefix="/api/system", tags=["system"])
app.include_router(chat.router, prefix="/api", tags=["chat"])


@app.get("/api/health")
async def health():
    return {
        "status": "online",
        "version": "0.1.0",
        "model_provider": settings.odin_model_provider,
        "model": settings.odin_model,
        "workspace": settings.odin_workspace,
        "tools_count": len(tool_registry),
        "agent_ready": odin_agent is not None and odin_agent.provider is not None,
    }
