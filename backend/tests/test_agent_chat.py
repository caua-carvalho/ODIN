"""OdinAgent loop tests.

Cover the behaviour the chat WebSocket relies on:

* a provider ``retry`` chunk is surfaced to the client as a ``status`` event;
* a cancelled turn (the user pressed "stop") persists the partial answer so
  the conversation history matches what the client already rendered.

The database is a throwaway SQLite file and the session factory the agent uses
is monkeypatched, so nothing touches the real ``odin.db``.
"""
import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("GEMINI_API_KEY", "test-key")

import app.agent.agent as agent_mod
from app.agent.agent import OdinAgent
from app.agent.providers.base import LLMChunk
from app.database.models import Base, Message
from app.tools.registry import ToolRegistry


@pytest.fixture
async def agent_db(monkeypatch, tmp_path):
    """A throwaway DB wired into the agent's ``get_db_session``."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def fake_session():
        async with Session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    monkeypatch.setattr(agent_mod, "get_db_session", fake_session)
    try:
        yield Session
    finally:
        await engine.dispose()


async def _assistant_messages(Session, conversation_id):
    async with Session() as session:
        result = await session.execute(
            select(Message).where(Message.conversation_id == conversation_id)
        )
        return [m for m in result.scalars().all() if m.role == "assistant"]


class _SlowProvider:
    """Streams one chunk, then hangs until cancelled."""

    def __init__(self):
        self.first_chunk = asyncio.Event()

    async def generate(self, messages, tools, system):
        yield LLMChunk(type="text", content="Partial answer")
        self.first_chunk.set()
        await asyncio.sleep(3600)
        yield LLMChunk(type="done")


class _ScriptedProvider:
    def __init__(self, chunks):
        self._chunks = chunks

    async def generate(self, messages, tools, system):
        for chunk in self._chunks:
            yield chunk


async def test_cancel_persists_partial_output(agent_db):
    Session = agent_db
    provider = _SlowProvider()
    agent = OdinAgent(provider=provider, tool_registry=ToolRegistry())
    conversation_id = "conv-cancel"
    events = []

    async def consume():
        async for event in agent.chat("hi", conversation_id):
            events.append(event)

    task = asyncio.create_task(consume())
    await asyncio.wait_for(provider.first_chunk.wait(), timeout=2)
    await asyncio.sleep(0.05)  # let the agent forward the chunk

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # No "done" — the turn was aborted, not completed.
    assert all(event["type"] != "done" for event in events)
    assert any(event["type"] == "text_chunk" for event in events)

    messages = await _assistant_messages(Session, conversation_id)
    assert len(messages) == 1
    assert messages[0].content == "Partial answer"


async def test_completed_turn_is_saved_once(agent_db):
    Session = agent_db
    provider = _ScriptedProvider(
        [
            LLMChunk(type="text", content="All "),
            LLMChunk(type="text", content="done."),
            LLMChunk(type="done"),
        ]
    )
    agent = OdinAgent(provider=provider, tool_registry=ToolRegistry())
    conversation_id = "conv-done"

    events = [event async for event in agent.chat("hi", conversation_id)]

    assert events[-1] == {"type": "done", "conversation_id": conversation_id}
    messages = await _assistant_messages(Session, conversation_id)
    assert len(messages) == 1
    assert messages[0].content == "All done."


async def test_retry_chunk_becomes_status_event(agent_db):
    provider = _ScriptedProvider(
        [
            LLMChunk(
                type="retry",
                content="Provider rate limited — retrying in 5s (1/3)…",
                retry_after=5.0,
            ),
            LLMChunk(type="text", content="ok"),
            LLMChunk(type="done"),
        ]
    )
    agent = OdinAgent(provider=provider, tool_registry=ToolRegistry())

    events = [event async for event in agent.chat("hi", "conv-retry")]

    statuses = [e for e in events if e["type"] == "status"]
    assert any("rate limited" in e["message"] for e in statuses)
