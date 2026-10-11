from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

import httpx
import websockets
from websockets.asyncio.client import ClientConnection

from app.config import settings


class OdinConfigError(RuntimeError):
    """Raised when the provider/model configuration API cannot be reached."""


class OdinClient:
    """WebSocket client for the Odin backend."""

    def __init__(self) -> None:
        self.conversation_id = str(uuid.uuid4())

    @property
    def url(self) -> str:
        return (
            f"ws://{settings.odin_host}:"
            f"{settings.odin_port}/api/ws/{self.conversation_id}"
        )

    async def connect(self) -> ClientConnection:
        return await websockets.connect(self.url)

    async def send_message(
        self,
        websocket: ClientConnection,
        content: str,
    ) -> AsyncIterator[dict]:
        await websocket.send(
            json.dumps(
                {
                    "type": "message",
                    "content": content,
                }
            )
        )

        async for raw_event in websocket:
            event = json.loads(raw_event)
            yield event

            if event.get("type") in {"done", "error"}:
                break


def _error_detail(response: httpx.Response) -> str:
    """Pull a readable message out of a FastAPI error response."""
    try:
        data = response.json()
    except ValueError:
        data = None
    if isinstance(data, dict) and data.get("detail"):
        return str(data["detail"])
    text = response.text.strip()
    return text[:300] if text else f"HTTP {response.status_code}"


class OdinConfigClient:
    """REST client for backend provider/model configuration."""

    def __init__(
        self,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url or (
            f"http://{settings.odin_host}:{settings.odin_port}"
        )
        self._transport = transport

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
                transport=self._transport,
            ) as client:
                response = await client.request(method, path, **kwargs)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            raise OdinConfigError(_error_detail(exc.response)) from exc
        except httpx.RequestError as exc:
            raise OdinConfigError(
                f"Não foi possível alcançar o backend em {self.base_url} "
                f"({exc}). O Odin está rodando?"
            ) from exc

    async def get_health(self) -> dict:
        return await self._request("GET", "/api/health")

    async def list_providers(self) -> dict:
        return await self._request("GET", "/api/providers")

    async def select(self, provider: str, model: str) -> dict:
        return await self._request(
            "POST",
            "/api/providers/select",
            json={"provider": provider, "model": model},
        )
