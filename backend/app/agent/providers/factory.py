"""Provider factory: the only place that knows which providers exist.

Adding a new provider:
1. Create an adapter in providers/ implementing LLMProvider
2. Register it in PROVIDER_BUILDERS below
"""

import logging
from typing import Callable

from app.agent.providers.base import LLMProvider
from app.config import Settings

logger = logging.getLogger("odin.agent.providers")


def _build_gemini(settings: Settings) -> LLMProvider:
    # Imported lazily so unused provider SDKs are never loaded.
    from app.agent.providers.gemini import GeminiProvider

    return GeminiProvider(model=settings.odin_model, api_key=settings.gemini_api_key)


def _build_ollama(settings: Settings) -> LLMProvider:
    from app.agent.providers.ollama import OllamaProvider

    return OllamaProvider(
        model=settings.odin_model,
        base_url=settings.ollama_base_url,
        think=settings.ollama_think,
    )


PROVIDER_BUILDERS: dict[str, Callable[[Settings], LLMProvider]] = {
    "gemini": _build_gemini,
    "ollama": _build_ollama,
}


def create_llm_provider(settings: Settings) -> LLMProvider:
    """Instantiate the provider selected by `settings.odin_model_provider`.

    Raises ValueError with an explicit message for unsupported providers
    or misconfiguration — never fails silently.
    """
    name = (settings.odin_model_provider or "").strip().lower()

    builder = PROVIDER_BUILDERS.get(name)
    if builder is None:
        supported = ", ".join(sorted(PROVIDER_BUILDERS))
        raise ValueError(
            f"Unsupported LLM provider: {name}. Supported providers: {supported}"
        )

    provider = builder(settings)  # may raise with a specific config error

    logger.info(f"LLM provider initialized: {name}")
    logger.info(f"LLM model: {settings.odin_model}")
    return provider
