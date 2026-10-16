"""Chat WebSocket route tests.

Focus on the turn-control path: a ``stop`` message must cancel the in-flight
generation, and the client must receive a ``done`` marked ``cancelled``. The
real agent is replaced by a stub so no LLM or database is involved.
"""
import asyncio
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from starlette.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("GEMINI_API_KEY", "test-key")

import app.main as main_mod
from app.api.routes import chat
from app.api.websocket import ws_manager


class _HangingAgent:
    """Streams one chunk, then hangs until its task is cancelled."""

    def __init__(self):
        self.cancelled = False

    async def chat(self, message, conversation_id):
        try:
            yield {"type": "status", "message": "Thinking..."}
            yield {"type": "text_chunk", "content": "partial"}
            await asyncio.sleep(3600)
            yield {"type": "done", "conversation_id": conversation_id}
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        finally:
            pass


def _client():
    app = FastAPI()
    app.include_router(chat.router, prefix="/api")
    return TestClient(app)


def test_stop_cancels_inflight_turn(monkeypatch):
    agent = _HangingAgent()
    monkeypatch.setattr(main_mod, "odin_agent", agent)

    with _client() as client:
        with client.websocket_connect("/api/ws/conv-stop") as ws:
            ws.send_json({"type": "message", "content": "hi"})
            first = ws.receive_json()
            second = ws.receive_json()
            assert first["type"] == "status"
            assert second == {"type": "text_chunk", "content": "partial"}

            ws.send_json({"type": "stop"})
            done = ws.receive_json()

    assert done == {"type": "done", "cancelled": True}
    assert agent.cancelled is True
    assert ws_manager.active_conversations() == []


def test_second_message_while_busy_is_rejected(monkeypatch):
    agent = _HangingAgent()
    monkeypatch.setattr(main_mod, "odin_agent", agent)

    with _client() as client:
        with client.websocket_connect("/api/ws/conv-busy") as ws:
            ws.send_json({"type": "message", "content": "first"})
            # Drain the two events the agent emits for the first turn.
            assert ws.receive_json()["type"] == "status"
            assert ws.receive_json()["type"] == "text_chunk"

            ws.send_json({"type": "message", "content": "second"})
            error = ws.receive_json()
            assert error["type"] == "error"
            assert "already in progress" in error["message"]

            ws.send_json({"type": "stop"})
            assert ws.receive_json()["type"] == "done"


def test_ping_pong(monkeypatch):
    monkeypatch.setattr(main_mod, "odin_agent", _HangingAgent())

    with _client() as client:
        with client.websocket_connect("/api/ws/conv-ping") as ws:
            ws.send_json({"type": "ping"})
            assert ws.receive_json() == {"type": "pong"}
