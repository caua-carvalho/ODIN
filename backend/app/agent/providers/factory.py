"""Provider factory: the only place that maps a provider name to an instance.

Since the LiteLLM migration every supported provider is served by a single
adapter, ``LiteLLMProvider``, which speaks the OpenAI chat-completions shape for
all vendors. ``PROVIDER_BUILDERS`` is derived from the catalog so the runtime
selector (``POST /api/providers/select``), ``/api/health`` and the CLI ``/model``
command keep validating provider names exactly as before.

Adding a new provider now means adding a ``ProviderMeta`` to
``providers/catalog.py`` — no new adapter class is required.
"""

import logging
from typing import Callable

from app.agent.providers import catalog
from app.agent.providers.base import LLMProvider
from app.config import Settings

logger = logging.getLogger("odin.agent.providers")


def _build_litellm(settings: Settings) -> LLMProvider:
    # Imported lazily: LiteLLM itself is heavy (~15s) and is only imported when
    # the provider actually reports (see litellm_provider._get_litellm).
    from app.agent.providers.litellm_provider import LiteLLMProvider

    return LiteLLMProvider.from_settings(settings)


PROVIDER_BUILDERS: dict[str, Callable[[Settings], LLMProvider]] = {
    name: _build_litellm for name in catalog.PROVIDERS
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
