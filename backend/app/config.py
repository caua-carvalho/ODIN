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
    odin_briefing_repos: str = "/home/caua/odin,/home/caua/odin-workspace"

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
