from pydantic_settings import BaseSettings
from pathlib import Path
from functools import lru_cache


class Settings(BaseSettings):
    # Workspace
    odin_workspace: str = "/home/caua/odin-workspace"

    # Server
    odin_host: str = "127.0.0.1"
    odin_port: int = 8000

    # LLM
    odin_model_provider: str = "gemini"
    odin_model: str = "gemini-2.0-flash"

    # API Keys
    gemini_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

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
