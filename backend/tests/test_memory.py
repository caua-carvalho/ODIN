"""Long-term memory tests (Phase 3).

Everything runs offline with fakes: the real Mem0 package is never imported and
no LLM/embedder is called.

Covers:
- ``MemoryService`` (recall/remember, error containment, empty inputs) over a
  fake backend;
- ``create_memory_service`` degradation (disabled -> None, missing Mem0 -> None,
  working backend -> service) and the Mem0 config assembly;
- the agent loop: recall is called and injected into the system prompt when
  memory is enabled, and nothing changes when it is disabled;
- the ``_load_history`` fix (the *most recent* messages are returned);
- tool-result truncation.
"""
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

import app.agent.agent as agent_mod
import app.agent.memory.service as service_mod
from app.agent.agent import (
    MAX_CONTEXT_MESSAGES,
    OdinAgent,
    _truncate_for_context,
)
from app.agent.memory import create_memory_service
from app.agent.memory.service import (
    MemoryService,
    _build_mem0_config,
    _extract_memory_texts,
    format_memory_context,
)
from app.agent.prompts.system import get_system_prompt
from app.agent.providers.base import LLMChunk
from app.config import Settings
from app.database.models import Base, Message
from app.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------
async def _make_factory(tmp_path):
    """Temp SQLite DB with all tables; return an async session factory."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


def _patch_db(monkeypatch, factory):
    """Point the agent module's ``get_db_session`` at a temp factory."""

    @asynccontextmanager
    async def fake_get_db_session():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    monkeypatch.setattr(agent_mod, "get_db_session", fake_get_db_session)


class _FakeBackend:
    """In-memory stand-in for a MemoryBackend (records calls, can fail)."""

    def __init__(self, results=None, fail=False):
        self.results = results if results is not None else []
        self.fail = fail
        self.searches: list[tuple] = []
        self.adds: list[tuple] = []

    async def search(self, query, *, user_id="odin", limit=5):
        self.searches.append((query, user_id, limit))
        if self.fail:
            raise RuntimeError("search boom")
        return self.results

    async def add(self, messages, *, user_id="odin"):
        self.adds.append((messages, user_id))
        if self.fail:
            raise RuntimeError("add boom")


class _FakeProvider:
    """Provider that replays a fixed list of chunks and records the request."""

    def __init__(self, chunks):
        self._chunks = chunks
        self.captured = None

    async def generate(self, messages, tools, system):
        self.captured = {"messages": messages, "tools": tools, "system": system}
        for chunk in self._chunks:
            yield chunk


class _FakeMemory:
    """Records recall/remember calls; returns canned memories."""

    def __init__(self, memories=None):
        self.memories = memories or []
        self.recall_calls: list[tuple] = []
        self.remember_calls: list[tuple] = []

    async def recall(self, query, *, conversation_id=None):
        self.recall_calls.append((query, conversation_id))
        return list(self.memories)

    async def remember(self, user_message, assistant_message, *, conversation_id=None):
        self.remember_calls.append((user_message, assistant_message, conversation_id))


# ---------------------------------------------------------------------------
# MemoryService
# ---------------------------------------------------------------------------
class TestMemoryService:
    async def test_recall_returns_texts(self):
        backend = _FakeBackend(results=[{"memory": "User likes dark mode"}])
        service = MemoryService(backend, user_id="odin", recall_limit=3)
        assert await service.recall("theme") == ["User likes dark mode"]
        assert backend.searches == [("theme", "odin", 3)]

    async def test_recall_blank_query_is_noop(self):
        backend = _FakeBackend()
        service = MemoryService(backend)
        assert await service.recall("   ") == []
        assert backend.searches == []

    async def test_recall_failure_is_contained(self):
        service = MemoryService(_FakeBackend(fail=True))
        assert await service.recall("anything") == []

    async def test_remember_forwards_the_exchange(self):
        backend = _FakeBackend()
        service = MemoryService(backend, user_id="alice")
        await service.remember("hi", "hello there", conversation_id="c1")
        messages, user_id = backend.adds[0]
        assert user_id == "alice"
        assert messages == [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello there"},
        ]

    async def test_remember_skips_empty_messages(self):
        backend = _FakeBackend()
        service = MemoryService(backend)
        await service.remember("", "answer")
        await service.remember("question", "   ")
        assert backend.adds == []

    async def test_remember_failure_is_contained(self):
        service = MemoryService(_FakeBackend(fail=True))
        # Must not raise.
        await service.remember("hi", "there")


class TestMemoryHelpers:
    def test_format_memory_context_empty(self):
        assert format_memory_context([]) == ""

    def test_format_memory_context_bullets(self):
        text = format_memory_context(["likes coffee", "uses vim"])
        assert "likes coffee" in text
        assert "- uses vim" in text

    def test_extract_memory_texts_handles_both_keys(self):
        records = [{"memory": "a"}, {"text": "b"}, {"memory": ""}, {"other": "x"}]
        assert _extract_memory_texts(records) == ["a", "b"]


# ---------------------------------------------------------------------------
# create_memory_service / config
# ---------------------------------------------------------------------------
class TestCreateMemoryService:
    def _settings(self, **overrides):
        values = dict(odin_memory_enabled=True, _env_file=None)
        values.update(overrides)
        return Settings(**values)

    def test_disabled_returns_none(self):
        s = Settings(odin_memory_enabled=False, _env_file=None)
        assert create_memory_service(s) is None

    def test_missing_mem0_degrades_to_none(self, monkeypatch):
        class _Boom:
            def __init__(self, settings):
                raise ImportError("No module named 'mem0'")

        monkeypatch.setattr(service_mod, "Mem0Backend", _Boom)
        assert create_memory_service(self._settings()) is None

    def test_backend_failure_degrades_to_none(self, monkeypatch):
        class _Boom:
            def __init__(self, settings):
                raise RuntimeError("vector store unavailable")

        monkeypatch.setattr(service_mod, "Mem0Backend", _Boom)
        assert create_memory_service(self._settings()) is None

    def test_builds_service_with_configured_backend(self, monkeypatch):
        created = {}

        class _FakeMem0:
            def __init__(self, settings):
                created["settings"] = settings

        monkeypatch.setattr(service_mod, "Mem0Backend", _FakeMem0)
        service = create_memory_service(
            self._settings(odin_memory_user_id="alice", odin_memory_recall_limit=9)
        )
        assert isinstance(service, MemoryService)
        assert service.user_id == "alice"
        assert service.recall_limit == 9


class TestMem0Config:
    def test_config_is_local_and_embedded(self):
        s = Settings(
            odin_memory_enabled=True,
            odin_memory_llm_model="qwen3:0.6b",
            odin_memory_embedder_model="nomic-embed-text",
            odin_memory_vector_store="chroma",
            ollama_base_url="http://localhost:11434",
            _env_file=None,
        )
        config = _build_mem0_config(s)
        assert config["llm"]["provider"] == "ollama"
        assert config["llm"]["config"]["model"] == "qwen3:0.6b"
        assert config["llm"]["config"]["ollama_base_url"] == "http://localhost:11434"
        assert config["embedder"]["provider"] == "ollama"
        assert config["embedder"]["config"]["model"] == "nomic-embed-text"
        assert config["vector_store"]["provider"] == "chroma"


# ---------------------------------------------------------------------------
# Agent loop integration
# ---------------------------------------------------------------------------
class TestAgentMemoryIntegration:
    async def test_recall_and_remember_when_enabled(self, tmp_path, monkeypatch):
        factory = await _make_factory(tmp_path)
        _patch_db(monkeypatch, factory)

        provider = _FakeProvider(
            [LLMChunk(type="text", content="Hi!"), LLMChunk(type="done")]
        )
        memory = _FakeMemory(["The user's name is Cauã"])
        agent = OdinAgent(
            provider=provider, tool_registry=ToolRegistry(), memory=memory
        )

        events = [e async for e in agent.chat("What's my name?", "c1")]

        # Recalled with the user's message, before the LLM call.
        assert memory.recall_calls == [("What's my name?", "c1")]
        # Memory injected into the system prompt (the only field the adapter
        # carries through for every provider).
        assert "The user's name is Cauã" in provider.captured["system"]
        # Write-back happened after the response.
        assert memory.remember_calls == [("What's my name?", "Hi!", "c1")]
        assert events[-1]["type"] == "done"

    async def test_disabled_memory_leaves_loop_unchanged(self, tmp_path, monkeypatch):
        factory = await _make_factory(tmp_path)
        _patch_db(monkeypatch, factory)

        provider = _FakeProvider(
            [LLMChunk(type="text", content="Hi!"), LLMChunk(type="done")]
        )
        # No memory service: the behaviour must be identical to before Phase 3.
        agent = OdinAgent(provider=provider, tool_registry=ToolRegistry())

        events = [e async for e in agent.chat("hi", "c1")]

        assert provider.captured["system"] == get_system_prompt()
        assert events[-1]["type"] == "done"

    async def test_no_memories_does_not_alter_system_prompt(self, tmp_path, monkeypatch):
        factory = await _make_factory(tmp_path)
        _patch_db(monkeypatch, factory)

        provider = _FakeProvider(
            [LLMChunk(type="text", content="ok"), LLMChunk(type="done")]
        )
        agent = OdinAgent(
            provider=provider,
            tool_registry=ToolRegistry(),
            memory=_FakeMemory([]),
        )
        async for _ in agent.chat("hi", "c1"):
            pass

        assert provider.captured["system"] == get_system_prompt()


# ---------------------------------------------------------------------------
# _load_history fix
# ---------------------------------------------------------------------------
class TestLoadHistory:
    async def test_returns_most_recent_in_chronological_order(self, tmp_path):
        factory = await _make_factory(tmp_path)
        base = datetime(2026, 1, 1, tzinfo=UTC)
        async with factory() as db:
            for i in range(60):
                db.add(
                    Message(
                        id=f"m{i:03d}",
                        conversation_id="c1",
                        role="user",
                        content=f"msg-{i}",
                        created_at=base + timedelta(seconds=i),
                    )
                )
            await db.commit()

        agent = OdinAgent(provider=None, tool_registry=ToolRegistry())
        async with factory() as db:
            history = await agent._load_history(db, "c1")

        assert len(history) == MAX_CONTEXT_MESSAGES
        # The oldest 10 are dropped; the last 50 are kept, oldest-first.
        assert [m.content for m in history] == [
            f"msg-{i}" for i in range(10, 60)
        ]
        assert history[-1].content == "msg-59"

    async def test_fewer_than_window_returns_all(self, tmp_path):
        factory = await _make_factory(tmp_path)
        base = datetime(2026, 1, 1, tzinfo=UTC)
        async with factory() as db:
            for i in range(3):
                db.add(
                    Message(
                        id=f"m{i}",
                        conversation_id="c1",
                        role="user",
                        content=f"msg-{i}",
                        created_at=base + timedelta(seconds=i),
                    )
                )
            await db.commit()

        agent = OdinAgent(provider=None, tool_registry=ToolRegistry())
        async with factory() as db:
            history = await agent._load_history(db, "c1")
        assert [m.content for m in history] == ["msg-0", "msg-1", "msg-2"]


# ---------------------------------------------------------------------------
# Tool-result truncation
# ---------------------------------------------------------------------------
class TestToolResultTruncation:
    def test_short_content_untouched(self):
        assert _truncate_for_context("small") == "small"

    def test_large_content_truncated_with_marker(self):
        content = "x" * (agent_mod.MAX_TOOL_RESULT_CHARS + 500)
        out = _truncate_for_context(content)
        assert len(out) < len(content)
        assert out.startswith("x" * 100)
        assert "truncated 500 chars" in out
