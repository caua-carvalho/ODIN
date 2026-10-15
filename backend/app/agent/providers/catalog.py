"""Provider catalog and runtime model selection.

This module owns two things:

1. **Static metadata** about the LLM providers Odin can talk to (`PROVIDERS`),
   including how to tell whether a provider is configured (API key) and which
   models to offer when dynamic discovery is unavailable.
2. **The active runtime selection** (`set_active` / `get_active`). The provider
   is a process-wide singleton, so the last successful switch is the one the
   agent uses for subsequent messages.

Model discovery is best-effort: Ollama is queried through its local HTTP API and
Gemini through the Google GenAI SDK. Discovery failures degrade to the curated
fallback list instead of breaking the endpoint.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.config import Settings, settings

logger = logging.getLogger("odin.agent.providers.catalog")


class ProviderMeta:
    """Static, immutable description of a provider."""

    __slots__ = (
        "id",
        "label",
        "description",
        "default_model",
        "api_key_setting",
        "fallback_models",
        "litellm_prefix",
    )

    def __init__(
        self,
        id: str,
        label: str,
        description: str,
        default_model: str,
        api_key_setting: str | None = None,
        fallback_models: tuple[str, ...] = (),
        litellm_prefix: str | None = None,
    ) -> None:
        self.id = id
        self.label = label
        self.description = description
        self.default_model = default_model
        # Settings attribute that must be non-empty for this provider to work,
        # or None when no credentials are needed (e.g. a local Ollama server).
        self.api_key_setting = api_key_setting
        self.fallback_models = fallback_models
        # LiteLLM routing prefix (``f"{prefix}/{model}"``). Defaults to the
        # provider id; only set it explicitly when the two differ.
        self.litellm_prefix = litellm_prefix or id


PROVIDERS: dict[str, ProviderMeta] = {
    "gemini": ProviderMeta(
        id="gemini",
        label="Google Gemini",
        description="Cloud models via the Google GenAI API",
        default_model="gemini-2.5-flash",
        api_key_setting="gemini_api_key",
        fallback_models=(
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
        ),
    ),
    "ollama": ProviderMeta(
        id="ollama",
        label="Ollama (local)",
        description="Local models served by Ollama",
        default_model="qwen3:0.6b",
        api_key_setting=None,
        fallback_models=("qwen3:0.6b",),
    ),
    "groq": ProviderMeta(
        id="groq",
        label="Groq",
        description="Fast cloud inference via the Groq OpenAI-compatible API",
        default_model="openai/gpt-oss-120b",
        api_key_setting="groq_api_key",
        fallback_models=(
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "allam-2-7b",
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "meta-llama/llama-4-maverick-17b-128e-instruct",
            "qwen/qwen3-32b",
            "moonshotai/kimi-k2-instruct",
        ),
    ),
    "openai": ProviderMeta(
        id="openai",
        label="OpenAI",
        description="OpenAI GPT models via the OpenAI API",
        default_model="gpt-4o-mini",
        api_key_setting="openai_api_key",
        fallback_models=("gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"),
    ),
    "anthropic": ProviderMeta(
        id="anthropic",
        label="Anthropic",
        description="Anthropic Claude models",
        default_model="claude-3-5-haiku-latest",
        api_key_setting="anthropic_api_key",
        fallback_models=(
            "claude-3-5-haiku-latest",
            "claude-3-5-sonnet-latest",
            "claude-sonnet-4-20250514",
        ),
    ),
}


class ActiveSelection:
    """The provider/model currently in use by the running agent."""

    __slots__ = ("provider", "model")

    def __init__(self, provider: str, model: str) -> None:
        self.provider = provider
        self.model = model

    def as_dict(self) -> dict[str, str]:
        return {"provider": self.provider, "model": self.model}


# Process-wide mutable state, set in the lifespan and on every switch.
_active: ActiveSelection | None = None


def set_active(provider: str, model: str) -> ActiveSelection:
    """Record the provider/model the agent is now using."""
    global _active
    _active = ActiveSelection(provider=(provider or "").strip().lower(), model=model)
    return _active


def get_active() -> ActiveSelection | None:
    return _active


def is_configured(meta: ProviderMeta, config: Settings | None = None) -> bool:
    """Whether the provider has everything it needs to run."""
    config = config or settings
    if meta.api_key_setting is None:
        return True
    return bool(getattr(config, meta.api_key_setting, ""))


def _merge_unique(*groups: list[str] | tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for group in groups:
        for item in group:
            if item and item not in seen:
                seen.add(item)
                merged.append(item)
    return merged


def parse_ollama_tags(data: dict) -> list[str]:
    """Extract model names from an Ollama `/api/tags` response."""
    names: list[str] = []
    for entry in data.get("models") or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name") or entry.get("model")
        if name:
            names.append(str(name))
    return names


async def _discover_ollama_models(config: Settings) -> list[str]:
    base_url = (config.ollama_base_url or "").rstrip("/")
    if not base_url:
        return []
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as client:
            response = await client.get("/api/tags")
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(f"Could not list Ollama models: {exc}")
        return []
    return parse_ollama_tags(data)


def _discover_gemini_models_sync(api_key: str) -> list[str]:
    """Blocking Gemini model listing; called via a worker thread."""
    from google import genai

    client = genai.Client(api_key=api_key)
    names: list[str] = []
    for model in client.models.list():
        raw = getattr(model, "name", "") or ""
        short = raw.split("/", 1)[1] if raw.startswith("models/") else raw
        if not short:
            continue
        lowered = short.lower()
        # Only keep text/chat models; drop embeddings and specialised
        # audio/image/research models that cannot drive the agent.
        blocked = (
            "embedding",
            "aqa",
            "imagen",
            "tts",
            "image",
            "lyria",
            "robotics",
            "computer-use",
            "deep-research",
            "transcribe",
            "nano-banana",
        )
        if any(token in lowered for token in blocked):
            continue
        actions = getattr(model, "supported_actions", None)
        if actions and "generateContent" not in actions:
            continue
        names.append(short)
    return names


async def _discover_gemini_models(config: Settings) -> list[str]:
    if not config.gemini_api_key:
        return []
    try:
        return await asyncio.to_thread(
            _discover_gemini_models_sync, config.gemini_api_key
        )
    except Exception as exc:  # discovery is best-effort
        logger.warning(f"Could not list Gemini models: {exc}")
        return []


async def _discover_groq_models(config: Settings) -> list[str]:
    api_key = config.groq_api_key
    base_url = (config.groq_base_url or "").rstrip("/")
    if not api_key or not base_url:
        return []
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as client:
            response = await client.get(
                "/models", headers={"Authorization": f"Bearer {api_key}"}
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(f"Could not list Groq models: {exc}")
        return []
    names: list[str] = []
    for entry in data.get("data") or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("id")
        if not name:
            continue
        # Drop non-chat models (speech/audio/guards) that cannot drive the agent.
        lowered = str(name).lower()
        if any(
            token in lowered
            for token in ("whisper", "tts", "guard", "embedding", "orpheus", "playai")
        ):
            continue
        names.append(str(name))
    return names


async def list_models(provider_id: str, config: Settings | None = None) -> list[str]:
    """Return the models offered for a provider.

    Discovery results are merged with the configured model and the currently
    active model so the user never loses the selection they are already on.
    """
    config = config or settings
    meta = PROVIDERS.get(provider_id)
    if meta is None:
        return []

    if provider_id == "ollama":
        discovered = await _discover_ollama_models(config)
    elif provider_id == "gemini":
        discovered = await _discover_gemini_models(config)
    elif provider_id == "groq":
        discovered = await _discover_groq_models(config)
    else:
        discovered = []

    pinned: list[str] = []
    active = get_active()
    if active and active.provider == provider_id:
        pinned.append(active.model)
    if config.odin_model_provider.strip().lower() == provider_id:
        pinned.append(config.odin_model)

    models = _merge_unique(discovered, pinned, meta.fallback_models)
    return models
