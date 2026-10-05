import uuid
from datetime import datetime, UTC
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.api.websocket import ws_manager

router = APIRouter()


@router.websocket("/ws/{conversation_id}")
async def websocket_chat(
    websocket: WebSocket,
    conversation_id: str,
):
    """WebSocket endpoint for streaming chat with Odin.

    Client sends: {"type": "message", "content": "user message"}
    Server streams: various event types (text_chunk, tool_start, tool_end, etc.)
    """
    from app.main import odin_agent  # avoid circular imports

    await ws_manager.connect(conversation_id, websocket)

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "message":
                user_content = data.get("content", "").strip()
                if not user_content:
                    await websocket.send_json({"type": "error", "message": "Empty message"})
                    continue

                # Stream agent response
                async for event in odin_agent.chat(
                    message=user_content,
                    conversation_id=conversation_id,
                ):
                    await websocket.send_json(event)

            elif data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        ws_manager.disconnect(conversation_id, websocket)
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
        ws_manager.disconnect(conversation_id, websocket)
