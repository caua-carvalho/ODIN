import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.websocket import ws_manager

logger = logging.getLogger("odin.api.chat")

router = APIRouter()


@router.websocket("/ws/{conversation_id}")
async def websocket_chat(
    websocket: WebSocket,
    conversation_id: str,
):
    """WebSocket endpoint for streaming chat with Odin.

    Client sends:
        {"type": "message", "content": "..."}  start a turn
        {"type": "stop"}                       cancel the in-flight turn
        {"type": "ping"}                       keep-alive

    Server streams: status / text_chunk / tool_start / tool_end /
    permission_request / permission_resolved / done / error events. A turn that
    the client stopped ends with {"type": "done", "cancelled": true}.
    """
    from app.main import odin_agent  # avoid circular imports

    await ws_manager.connect(conversation_id, websocket)

    # The generation runs in its own task so the receive loop stays responsive
    # to a "stop" while the model is streaming. Sends are serialised because
    # both the generation task and the receive loop (pong) can write here.
    send_lock = asyncio.Lock()
    generation_task: asyncio.Task | None = None

    async def send(payload: dict) -> None:
        async with send_lock:
            await websocket.send_json(payload)

    async def run_generation(user_content: str) -> None:
        stream = odin_agent.chat(
            message=user_content,
            conversation_id=conversation_id,
        )
        try:
            async for event in stream:
                await send(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Chat generation failed")
            try:
                await send({"type": "error", "message": str(exc)})
            except Exception:
                pass
        finally:
            # Verifies the agent generator is closed so a cancelled turn still
            # persists its partial output and releases the upstream LLM stream.
            try:
                await stream.aclose()
            except asyncio.CancelledError:
                pass
            except Exception:  # pragma: no cover - best effort
                pass

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "message":
                user_content = (data.get("content") or "").strip()
                if not user_content:
                    await send({"type": "error", "message": "Empty message"})
                    continue
                if generation_task is not None and not generation_task.done():
                    await send(
                        {
                            "type": "error",
                            "message": "A response is already in progress.",
                        }
                    )
                    continue
                generation_task = asyncio.create_task(run_generation(user_content))

            elif msg_type == "stop":
                if generation_task is not None and not generation_task.done():
                    generation_task.cancel()
                    try:
                        await generation_task
                    except asyncio.CancelledError:
                        # The agent already persisted any partial output.
                        await send({"type": "done", "cancelled": True})
                    except Exception:  # pragma: no cover - defensive
                        logger.exception("Error while cancelling generation")

            elif msg_type == "ping":
                await send({"type": "pong"})

    except WebSocketDisconnect:
        pass
    finally:
        if generation_task is not None and not generation_task.done():
            generation_task.cancel()
            try:
                await generation_task
            except (asyncio.CancelledError, Exception):
                pass
        ws_manager.disconnect(conversation_id, websocket)
