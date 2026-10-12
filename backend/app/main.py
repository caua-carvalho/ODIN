import logging
import logging.config
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database.session import init_db
from app.agent.agent import OdinAgent
from app.agent.providers import catalog, create_llm_provider
from app.tools.registry import ToolRegistry
from app.tools.filesystem.tools import create_filesystem_tools
from app.tools.shell.tools import ExecuteCommandTool
from app.tools.projects.tools import create_project_tools
from app.security.path_guard import PathGuard
from app.security.policy import SecurityPolicy
from app.security.auth import TokenAuthMiddleware
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

    for project_tool in create_project_tools(security_policy):
        tool_registry.register(project_tool)

    logger.info(f"Registered {len(tool_registry)} tools: {tool_registry.names()}")

    # Initialize LLM provider (selection lives in providers/factory.py)
    provider = create_llm_provider(settings)
    # Record the active selection so /api/health and the selectors can report it.
    catalog.set_active(settings.odin_model_provider, settings.odin_model)

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

# Optional API token. Registered BEFORE CORS so that CORSMiddleware is added
# last and stays the outermost layer — it must answer preflight OPTIONS
# requests (which carry no Authorization header) before the auth gate runs.
if settings.odin_api_token:
    app.add_middleware(TokenAuthMiddleware, token=settings.odin_api_token)
    logger.info("API token authentication enabled (ODIN_API_TOKEN set)")

# CORS
# Explicit origin allow-list plus a regex that also accepts dev clients served
# from a private LAN address (e.g. Expo web at http://192.168.0.10:8081).
_cors_origins = [
    origin.strip() for origin in settings.odin_cors_origins.split(",") if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=settings.odin_cors_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
from app.api.routes import conversations, tools, skills, permissions, mcp, system, chat, providers, briefing, projects

app.include_router(conversations.router, prefix="/api/conversations", tags=["conversations"])
app.include_router(projects.router, prefix="/api", tags=["projects"])
app.include_router(tools.router, prefix="/api/tools", tags=["tools"])
app.include_router(skills.router, prefix="/api/skills", tags=["skills"])
app.include_router(permissions.router, prefix="/api/permissions", tags=["permissions"])
app.include_router(mcp.router, prefix="/api/mcp", tags=["mcp"])
app.include_router(system.router, prefix="/api/system", tags=["system"])
app.include_router(providers.router, prefix="/api/providers", tags=["providers"])
app.include_router(briefing.router, prefix="/api/briefing", tags=["briefing"])
app.include_router(chat.router, prefix="/api", tags=["chat"])


@app.get("/api/health")
async def health():
    active = catalog.get_active()
    return {
        "status": "online",
        "version": "0.1.0",
        "model_provider": active.provider if active else settings.odin_model_provider,
        "model": active.model if active else settings.odin_model,
        "workspace": settings.odin_workspace,
        "tools_count": len(tool_registry),
        "agent_ready": odin_agent is not None and odin_agent.provider is not None,
    }


# ---------------------------------------------------------------------------
# Web panel (built frontend)
# ---------------------------------------------------------------------------
# Serve the Vite build so the console is available on the same origin as the
# API (http://127.0.0.1:8000). The panel is a React SPA, so any unknown
# non-API path falls back to index.html for client-side routing.
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

if FRONTEND_DIST.is_dir():
    _assets_dir = FRONTEND_DIST / "assets"
    if _assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_web_panel(full_path: str) -> FileResponse:
        candidate = (FRONTEND_DIST / full_path).resolve()
        if (
            full_path
            and candidate.is_file()
            and candidate.is_relative_to(FRONTEND_DIST.resolve())
        ):
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")

    logger.info(f"Web panel served from {FRONTEND_DIST}")
else:
    logger.warning(
        "frontend/dist not found — the web panel will not be served. "
        "Run `npm run build` inside frontend/ to generate it."
    )
