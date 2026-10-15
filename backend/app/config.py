from pydantic_settings import BaseSettings
from pathlib import Path
from functools import lru_cache

# Repository root (…/odin). Used to locate the .env regardless of the current
# working directory the server happens to be started from.
REPO_ROOT = Path(__file__).resolve().parents[2]


def _default_workspace() -> str:
    """Portable default workspace next to the user's home directory."""
    return str(Path.home() / "odin-workspace")


class Settings(BaseSettings):
    # Workspace - Odin has full autonomy inside this directory. Defaults to
    # ~/odin-workspace so the project is not tied to a specific developer's
    # absolute path; override with ODIN_WORKSPACE in .env.
    odin_workspace: str = _default_workspace()

    # Server
    odin_host: str = "127.0.0.1"
    odin_port: int = 8000
    # Comma-separated list of browser origins allowed by CORS. Includes the
    # Vite dev server (3000) and the Expo web dev server (8081). Native mobile
    # clients (Expo Go) do not enforce CORS.
    odin_cors_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:8081,http://127.0.0.1:8081"
    )
    # Regex matched against request origins in addition to the explicit list
    # above. The default covers dev clients served from localhost or a private
    # LAN address (e.g. Expo web opened via http://192.168.x.x:8081).
    odin_cors_origin_regex: str = (
        r"^http://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|"
        r"192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)(?::\d+)?$"
    )

    # LLM
    odin_model_provider: str = "gemini"
    odin_model: str = "gemini-2.5-flash"

    # API Keys / provider-specific settings
    gemini_api_key: str = ""
    groq_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    ollama_base_url: str = "http://localhost:11434"
    # Ollama "think" parameter. Reasoning models (e.g. qwen3) return empty
    # responses/tool calls with thinking enabled, so the default is false.
    ollama_think: bool = False

    # Daily briefing
    odin_weather_city: str = "São José dos Campos"
    odin_weather_lat: float = -23.1794
    odin_weather_lon: float = -45.8869
    # Comma-separated list of repository paths to summarise in the briefing.
    # Empty by default so the app is portable; set ODIN_BRIEFING_REPOS in .env.
    odin_briefing_repos: str = ""

    # Database
    database_url: str = "sqlite+aiosqlite:///./odin.db"

    # Security
    # Optional bearer token required for /api/* (empty = disabled). Enable it
    # before exposing Odin to the LAN/internet (e.g. for the mobile app or a
    # remote ODIN_HOST). The mobile client stores it in its settings screen.
    odin_api_token: str = ""
    # Failed-token attempts allowed per client (window below) before the API
    # answers 429. Only counts failures; a correct token resets the counter.
    odin_auth_max_failures: int = 10
    odin_auth_window_seconds: int = 60

    # Web panel login sessions.
    # The panel exchanges ODIN_API_TOKEN for a signed session token (see
    # POST /api/auth/login) so it does not have to keep the raw token in
    # localStorage. Empty = derive the signing secret from ODIN_API_TOKEN.
    odin_session_secret: str = ""
    # Session lifetime when "remember me" is checked (days) or unchecked
    # (hours). Changing ODIN_SESSION_SECRET/ODIN_API_TOKEN invalidates sessions.
    odin_session_ttl_days: int = 7
    odin_session_ttl_hours: int = 12

    # Debug
    debug: bool = False

    model_config = {
        # Absolute path: the server works from any working directory.
        "env_file": str(REPO_ROOT / ".env"),
        "extra": "ignore",
    }

    @property
    def workspace_path(self) -> Path:
        return Path(self.odin_workspace).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
