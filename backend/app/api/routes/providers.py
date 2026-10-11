"""Provider/model configuration API.

Exposes the provider catalog and the runtime switch used by both the frontend
TopBar selector and the terminal `/model` command.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agent.providers import catalog
from app.agent.providers import create_llm_provider
from app.agent.providers.factory import PROVIDER_BUILDERS
from app.config import settings

logger = logging.getLogger("odin.api.providers")

router = APIRouter()


class ProviderResponse(BaseModel):
    id: str
    label: str
    description: str
    configured: bool
    models: list[str]


class ActiveSelectionResponse(BaseModel):
    provider: str
    model: str


class ProvidersResponse(BaseModel):
    providers: list[ProviderResponse]
    active: ActiveSelectionResponse


class SelectRequest(BaseModel):
    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)


def _current_active() -> catalog.ActiveSelection:
    active = catalog.get_active()
    if active is not None:
        return active
    # Fallback for the brief window before the lifespan sets the active state.
    return catalog.ActiveSelection(
        provider=settings.odin_model_provider.strip().lower(),
        model=settings.odin_model,
    )


@router.get("", response_model=ProvidersResponse)
async def list_providers() -> ProvidersResponse:
    """List every known provider, its availability and its models."""
    active = _current_active()

    providers: list[ProviderResponse] = []
    for meta in catalog.PROVIDERS.values():
        providers.append(
            ProviderResponse(
                id=meta.id,
                label=meta.label,
                description=meta.description,
                configured=catalog.is_configured(meta),
                models=await catalog.list_models(meta.id),
            )
        )

    return ProvidersResponse(
        providers=providers,
        active=ActiveSelectionResponse(provider=active.provider, model=active.model),
    )


@router.post("/select", response_model=ActiveSelectionResponse)
async def select_provider(payload: SelectRequest) -> ActiveSelectionResponse:
    """Switch the active provider/model at runtime (process-wide)."""
    name = payload.provider.strip().lower()
    model = payload.model.strip()

    if name not in PROVIDER_BUILDERS:
        supported = ", ".join(sorted(PROVIDER_BUILDERS))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported LLM provider: {name}. Supported providers: {supported}",
        )

    meta = catalog.PROVIDERS.get(name)
    if meta is not None and not catalog.is_configured(meta):
        raise HTTPException(
            status_code=400,
            detail=f"Provider '{name}' is not configured (missing API key).",
        )

    # Reuse the factory by building a Settings copy with the requested selection.
    provider_settings = settings.model_copy(
        update={"odin_model_provider": name, "odin_model": model}
    )
    try:
        provider = create_llm_provider(provider_settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Imported lazily: the agent singleton lives in main and is created at startup.
    from app.main import odin_agent

    if odin_agent is None:
        raise HTTPException(status_code=503, detail="Agent is not ready")

    odin_agent.provider = provider
    active = catalog.set_active(name, model)
    logger.info(f"Active LLM provider switched to {active.provider} / {active.model}")

    return ActiveSelectionResponse(provider=active.provider, model=active.model)
