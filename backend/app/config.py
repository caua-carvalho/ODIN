from pydantic_settings import BaseSettings
from pathlib import Path
from functools import lru_cache


class Settings(BaseSettings):
    # Workspace
    odin_workspace: str = "/home/caua/odin-workspace"

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

    # Database
    database_url: str = "sqlite+aiosqlite:///./odin.db"

    # Debug
    debug: bool = False

    model_config = {"env_file": "../.env", "extra": "ignore"}

    @property
    def workspace_path(self) -> Path:
        return Path(self.odin_workspace).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
