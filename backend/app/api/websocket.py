import logging
from typing import Dict, List
from fastapi import WebSocket

logger = logging.getLogger("odin.api.websocket_manager")


class WebSocketManager:
    """Manages active WebSocket connections grouped by conversation."""

    def __init__(self) -> None:
        self._connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, conversation_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        if conversation_id not in self._connections:
            self._connections[conversation_id] = []
        self._connections[conversation_id].append(websocket)
        logger.info(f"WebSocket connected: conversation={conversation_id}")

    def disconnect(self, conversation_id: str, websocket: WebSocket) -> None:
        if conversation_id in self._connections:
            self._connections[conversation_id].discard(websocket) if hasattr(
                self._connections[conversation_id], "discard"
            ) else None
            try:
                self._connections[conversation_id].remove(websocket)
            except ValueError:
                pass
            if not self._connections[conversation_id]:
                del self._connections[conversation_id]
        logger.info(f"WebSocket disconnected: conversation={conversation_id}")

    async def broadcast_to_conversation(
        self, conversation_id: str, data: dict
    ) -> None:
        """Send a message to all sockets watching a conversation."""
        sockets = self._connections.get(conversation_id, [])
        dead = []
        for ws in sockets:
            try:
                await ws.send_json(data)
            except Exception as e:
                logger.warning(f"WebSocket send failed: {e}")
                dead.append(ws)
        for ws in dead:
            self.disconnect(conversation_id, ws)

    def active_conversations(self) -> list[str]:
        return list(self._connections.keys())


# Singleton
ws_manager = WebSocketManager()
