from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

import websockets
from websockets.asyncio.client import ClientConnection

from app.config import settings


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