"""Long-term memory tests (Phase 3, extended for issue #27).

Everything runs offline with fakes: the real Mem0 package is never imported and
no LLM/embedder is called (the Mem0 backend is exercised through a synchronous
fake client, mirroring the API-adaptation tests).

Covers:
- ``MemoryService`` full CRUD (remember/recall/list/update/forget) over a fake
  backend, plus error containment and empty inputs;
- metadata: origin/source/created_at are persisted, search hits carry their
  relevance score, and confidence is stored only when supplied (never invented);
- the ``_to_records`` / ``_build_memory_metadata`` helpers;
- the Mem0 backend's API adaptation for the new ``get_all`` / ``update`` /
  ``delete`` calls;
- the explicit ``memory`` agent tool: its contract, every action, its
  no-approval classification and its registration via ``create_memory_tools``;
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
    SOURCE_CONVERSATION,
    SOURCE_TOOL,
    MemoryRecord,
    MemoryService,
    _as_float,
    _build_mem0_config,
    _build_memory_metadata,
    _disable_thinking,
    _extract_memory_texts,
    _to_records,
    format_memory_context,
)
from app.agent.prompts.system import get_system_prompt
from app.agent.providers.base import LLMChunk
from app.config import Settings
from app.database.models import Base, Message
from app.tools.memory.tools import MemoryTool, create_memory_tools
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

    def __init__(self, results=None, fail=False, records=None):
        # ``results`` is returned by search; ``records`` by list_memories.
        self.results = results if results is not None else []
        self.records = records if records is not None else []
        self.fail = fail
        self.searches: list[tuple] = []
        self.adds: list[tuple] = []
        self.lists: list[tuple] = []
        self.updates: list[tuple] = []
        self.deletes: list[str] = []
        # Canned mutation results (tests override as needed).
        self.add_result: list[dict] | None = None
        self.update_result = True
        self.delete_result = True

    async def search(self, query, *, user_id="odin", limit=5, origin=None):
        self.searches.append((query, user_id, limit, origin))
        if self.fail:
            raise RuntimeError("search boom")
        return self.results

    async def add(self, messages, *, user_id="odin", metadata=None):
        self.adds.append((messages, user_id, metadata))
        if self.fail:
            raise RuntimeError("add boom")
        return self.add_result if self.add_result is not None else []

    async def list_memories(self, *, user_id="odin", limit=100, origin=None):
        self.lists.append((user_id, limit, origin))
        if self.fail:
            raise RuntimeError("list boom")
        return self.records

    async def update(self, memory_id, *, text=None, metadata=None):
        self.updates.append((memory_id, text, metadata))
        if self.fail:
            raise RuntimeError("update boom")
        return self.update_result

    async def delete(self, memory_id):
        self.deletes.append(memory_id)
        if self.fail:
            raise RuntimeError("delete boom")
        return self.delete_result


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


class _RecordingMemory:
    """Records MemoryService calls for the tool contract tests.

    Implements only the methods the tool uses, so an accidental call to a wrong
    method fails loudly (AttributeError) instead of silently passing.
    """

    def __init__(self, records=None):
        self.records = list(records or [])
        self.calls: list[tuple] = []
        self.update_result = True
        self.forget_result = True

    async def remember_text(self, text, *, origin=None, source="tool", confidence=None):
        self.calls.append(("remember_text", text, origin, source, confidence))
        return list(self.records)

    async def recall_records(self, query, *, origin=None, limit=None):
        self.calls.append(("recall_records", query, origin, limit))
        return list(self.records)

    async def list_memories(self, *, origin=None, limit=None):
        self.calls.append(("list_memories", origin, limit))
        return list(self.records)

    async def update(self, memory_id, *, text=None, origin=None, source=None, confidence=None):
        self.calls.append(("update", memory_id, text, origin, source, confidence))
        return self.update_result

    async def forget(self, memory_id):
        self.calls.append(("forget", memory_id))
        return self.forget_result


# ---------------------------------------------------------------------------
# MemoryService
# ---------------------------------------------------------------------------
class TestMemoryServiceRead:
    async def test_recall_returns_texts(self):
        backend = _FakeBackend(results=[{"memory": "User likes dark mode"}])
        service = MemoryService(backend, user_id="odin", recall_limit=3)
        assert await service.recall("theme") == ["User likes dark mode"]
        assert backend.searches == [("theme", "odin", 3, None)]

    async def test_recall_blank_query_is_noop(self):
        backend = _FakeBackend()
        service = MemoryService(backend)
        assert await service.recall("   ") == []
        assert backend.searches == []

    async def test_recall_failure_is_contained(self):
        service = MemoryService(_FakeBackend(fail=True))
        assert await service.recall("anything") == []

    async def test_recall_forwards_origin_filter_and_limit(self):
        backend = _FakeBackend()
        service = MemoryService(backend, recall_limit=3)
        await service.recall("theme", origin="c1", limit=7)
        assert backend.searches == [("theme", "odin", 7, "c1")]

    async def test_recall_records_annotates_relevance_and_metadata(self):
        backend = _FakeBackend(
            results=[
                {
                    "id": "m1",
                    "memory": "User likes dark mode",
                    "score": 0.87,
                    "metadata": {
                        "origin": "c1",
                        "source": "conversation",
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "confidence": 0.9,
                    },
                }
            ]
        )
        service = MemoryService(backend)
        records = await service.recall_records("theme")
        assert len(records) == 1
        record = records[0]
        assert record.memory == "User likes dark mode"
        assert record.id == "m1"
        assert record.origin == "c1"
        assert record.source == "conversation"
        assert record.relevance == 0.87
        assert record.confidence == 0.9
        assert record.created_at == "2026-01-01T00:00:00+00:00"

    async def test_list_memories_uses_default_limit_and_origin(self):
        backend = _FakeBackend(records=[{"id": "m1", "memory": "a"}])
        service = MemoryService(backend, list_limit=42)
        records = await service.list_memories(origin="c1")
        assert backend.lists == [("odin", 42, "c1")]
        assert [r.memory for r in records] == ["a"]

    async def test_list_memories_failure_is_contained(self):
        service = MemoryService(_FakeBackend(fail=True))
        assert await service.list_memories() == []


class TestMemoryServiceWrite:
    async def test_remember_forwards_the_exchange_and_metadata(self):
        backend = _FakeBackend()
        service = MemoryService(backend, user_id="alice")
        await service.remember("hi", "hello there", conversation_id="c1")
        messages, user_id, metadata = backend.adds[0]
        assert user_id == "alice"
        assert messages == [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello there"},
        ]
        # Origin (the conversation id) and source are persisted, with a timestamp.
        assert metadata["origin"] == "c1"
        assert metadata["source"] == SOURCE_CONVERSATION
        assert metadata["created_at"]
        assert "confidence" not in metadata

    async def test_remember_returns_written_records(self):
        backend = _FakeBackend()
        backend.add_result = [{"id": "m9", "memory": "User lives in Brazil"}]
        service = MemoryService(backend)
        records = await service.remember("where do I live?", "Brazil")
        assert [r.id for r in records] == ["m9"]
        assert records[0].memory == "User lives in Brazil"

    async def test_remember_skips_empty_messages(self):
        backend = _FakeBackend()
        service = MemoryService(backend)
        await service.remember("", "answer")
        await service.remember("question", "   ")
        assert backend.adds == []

    async def test_remember_failure_is_contained(self):
        service = MemoryService(_FakeBackend(fail=True))
        # Must not raise, and returns no records.
        assert await service.remember("hi", "there") == []

    async def test_remember_text_uses_tool_source_and_confidence(self):
        backend = _FakeBackend()
        service = MemoryService(backend)
        await service.remember_text(
            "Prefers metric units", origin="c2", confidence=0.8
        )
        messages, user_id, metadata = backend.adds[0]
        assert messages == [{"role": "user", "content": "Prefers metric units"}]
        assert metadata["origin"] == "c2"
        assert metadata["source"] == SOURCE_TOOL
        assert metadata["confidence"] == 0.8

    async def test_store_metadata_disabled_writes_none(self):
        backend = _FakeBackend()
        service = MemoryService(backend, store_metadata=False)
        await service.remember("hi", "there", conversation_id="c1")
        assert backend.adds[0][2] is None

    async def test_update_forwards_id_text_and_metadata(self):
        backend = _FakeBackend()
        service = MemoryService(backend)
        ok = await service.update("m1", text="new text", confidence=0.5)
        assert ok is True
        memory_id, text, metadata = backend.updates[0]
        assert memory_id == "m1"
        assert text == "new text"
        assert metadata["confidence"] == 0.5
        assert metadata["updated_at"]

    async def test_update_with_nothing_to_change_is_a_noop(self):
        backend = _FakeBackend()
        service = MemoryService(backend)
        assert await service.update("m1") is False
        assert await service.update("") is False
        assert backend.updates == []

    async def test_update_failure_is_contained(self):
        service = MemoryService(_FakeBackend(fail=True))
        assert await service.update("m1", text="x") is False

    async def test_forget_forwards_id(self):
        backend = _FakeBackend()
        service = MemoryService(backend)
        assert await service.forget("m1") is True
        assert backend.deletes == ["m1"]

    async def test_forget_blank_id_and_failure(self):
        service = MemoryService(_FakeBackend(fail=True))
        assert await service.forget("") is False
        assert await service.forget("m1") is False


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

    def test_build_memory_metadata_defaults_origin_to_unknown(self):
        metadata = _build_memory_metadata(origin=None, source=SOURCE_CONVERSATION)
        assert metadata["origin"] == "unknown"
        assert metadata["source"] == SOURCE_CONVERSATION
        assert metadata["created_at"]
        assert "confidence" not in metadata

    def test_build_memory_metadata_includes_confidence_when_given(self):
        metadata = _build_memory_metadata(
            origin="c1", source=SOURCE_TOOL, confidence=0.25
        )
        assert metadata["origin"] == "c1"
        assert metadata["source"] == SOURCE_TOOL
        assert metadata["confidence"] == 0.25

    def test_to_records_reads_metadata_and_backend_timestamps(self):
        records = _to_records(
            [
                {
                    "id": "m1",
                    "memory": "fact",
                    "created_at": "2026-02-02T00:00:00+00:00",
                    "metadata": {"origin": "c9", "source": "tool", "confidence": "0.7"},
                },
                {"memory": ""},  # dropped (no text)
                {"other": "x"},  # dropped (no text)
            ]
        )
        assert len(records) == 1
        record = records[0]
        assert record.id == "m1"
        # Top-level backend field wins for the timestamp ...
        assert record.created_at == "2026-02-02T00:00:00+00:00"
        # ... while origin/source/confidence come from metadata.
        assert record.origin == "c9"
        assert record.source == "tool"
        assert record.confidence == 0.7
        assert record.relevance is None

    def test_to_records_reads_relevance_from_score(self):
        records = _to_records(
            [{"id": "m1", "memory": "fact", "score": 0.5}], relevance_key="score"
        )
        assert records[0].relevance == 0.5

    def test_to_records_to_dict_is_jsonable(self):
        record = MemoryRecord(memory="fact", id="m1", origin="c1")
        assert record.to_dict()["memory"] == "fact"
        assert record.to_dict()["origin"] == "c1"

    def test_as_float_rejects_bools_and_garbage(self):
        assert _as_float(0.5) == 0.5
        assert _as_float("0.5") == 0.5
        assert _as_float(None) is None
        assert _as_float(True) is None
        assert _as_float("nope") is None


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
            self._settings(
                odin_memory_user_id="alice",
                odin_memory_recall_limit=9,
                odin_memory_list_limit=33,
                odin_memory_store_metadata=False,
            )
        )
        assert isinstance(service, MemoryService)
        assert service.user_id == "alice"
        assert service.recall_limit == 9
        assert service.list_limit == 33
        assert service.store_metadata is False

    def test_list_limit_and_metadata_defaults(self, monkeypatch):
        class _FakeMem0:
            def __init__(self, settings):
                pass

        monkeypatch.setattr(service_mod, "Mem0Backend", _FakeMem0)
        service = create_memory_service(self._settings())
        assert service.list_limit == 100
        assert service.store_metadata is True


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

    def test_remote_provider_uses_matching_api_key(self):
        s = Settings(
            odin_memory_enabled=True,
            odin_memory_llm_provider="groq",
            odin_memory_llm_model="openai/gpt-oss-120b",
            groq_api_key="gsk-test",
            _env_file=None,
        )
        llm = _build_mem0_config(s)["llm"]
        assert llm["provider"] == "groq"
        assert llm["config"]["model"] == "openai/gpt-oss-120b"
        assert llm["config"]["api_key"] == "gsk-test"
        assert llm["config"]["max_tokens"] == s.odin_memory_llm_max_tokens
        # The embedder stays local regardless of the LLM provider.
        assert _build_mem0_config(s)["embedder"]["provider"] == "ollama"

    def test_remote_provider_without_key_omits_api_key(self):
        s = Settings(
            odin_memory_enabled=True,
            odin_memory_llm_provider="openai",
            odin_memory_llm_model="gpt-4o-mini",
            openai_api_key="",
            _env_file=None,
        )
        llm = _build_mem0_config(s)["llm"]
        assert llm["provider"] == "openai"
        assert "api_key" not in llm["config"]


class TestMem0ApiAdaptation:
    """Mem0 2.x moved entities into ``filters`` and renamed ``limit`` to ``top_k``.

    The backend introspects the installed API so both shapes work. These tests
    use fake clients (no mem0 import, no network).
    """

    def _backend_with(self, client):
        backend = object.__new__(service_mod.Mem0Backend)
        backend._memory = client
        return backend

    def test_new_api_uses_filters_and_top_k(self):
        class _NewMemory:
            def search(self, query, *, top_k=20, filters=None, **kwargs):
                return {}

            def add(self, messages, *, user_id=None, metadata=None):
                return None

        backend = self._backend_with(_NewMemory())
        assert backend._search_kwargs("odin", 5) == {
            "filters": {"user_id": "odin"},
            "top_k": 5,
        }
        assert backend._add_kwargs("odin") == {"user_id": "odin"}

    def test_legacy_api_uses_user_id_and_limit(self):
        class _OldMemory:
            def search(self, query, *, user_id=None, limit=100):
                return {}

            def add(self, messages, *, filters=None):
                return None

        backend = self._backend_with(_OldMemory())
        assert backend._search_kwargs("odin", 5) == {"user_id": "odin", "limit": 5}
        assert backend._add_kwargs("odin") == {"filters": {"user_id": "odin"}}

    def test_infer_flag_is_forwarded_when_supported(self):
        class _Memory:
            def search(self, query, *, filters=None, top_k=20):
                return {}

            def add(self, messages, *, user_id=None, infer=True):
                return None

        backend = self._backend_with(_Memory())
        backend._infer = False
        assert backend._add_kwargs("odin") == {"user_id": "odin", "infer": False}

    def test_infer_defaults_to_true_on_the_class(self):
        from app.agent.memory.service import Mem0Backend

        assert Mem0Backend._infer is True

    def test_metadata_is_forwarded_to_add_when_supported(self):
        class _NewMemory:
            def add(self, messages, *, user_id=None, metadata=None):
                return None

        backend = self._backend_with(_NewMemory())
        assert backend._add_kwargs("odin", {"origin": "c1"}) == {
            "user_id": "odin",
            "metadata": {"origin": "c1"},
        }
        # No metadata -> the kwarg is omitted entirely.
        assert backend._add_kwargs("odin", None) == {"user_id": "odin"}

    def test_metadata_is_dropped_when_add_does_not_accept_it(self):
        class _OldMemory:
            def add(self, messages, *, filters=None):
                return None

        backend = self._backend_with(_OldMemory())
        assert backend._add_kwargs("odin", {"origin": "c1"}) == {
            "filters": {"user_id": "odin"}
        }

    def test_origin_becomes_a_filter_on_the_new_api(self):
        class _NewMemory:
            def search(self, query, *, top_k=20, filters=None):
                return {}

        backend = self._backend_with(_NewMemory())
        assert backend._search_kwargs("odin", 5, "c1") == {
            "filters": {"user_id": "odin", "origin": "c1"},
            "top_k": 5,
        }
        # No origin -> user scoping only.
        assert backend._search_kwargs("odin", 5, None) == {
            "filters": {"user_id": "odin"},
            "top_k": 5,
        }

    def test_list_kwargs_new_and_legacy(self):
        class _NewMemory:
            def get_all(self, *, filters=None, top_k=20):
                return {}

        class _OldMemory:
            def get_all(self, user_id=None, limit=100):
                return {}

        assert self._backend_with(_NewMemory())._list_kwargs("odin", 10, "c1") == {
            "filters": {"user_id": "odin", "origin": "c1"},
            "top_k": 10,
        }
        assert self._backend_with(_OldMemory())._list_kwargs("odin", 10) == {
            "user_id": "odin",
            "limit": 10,
        }

    def test_update_kwargs_prefer_text_and_fall_back_to_data(self):
        class _NewMemory:
            def update(self, memory_id, text=None, metadata=None):
                return {}

        class _OldMemory:
            def update(self, memory_id, data=None):
                return {}

        assert self._backend_with(_NewMemory())._update_kwargs("t", {"a": 1}) == {
            "text": "t",
            "metadata": {"a": 1},
        }
        assert self._backend_with(_OldMemory())._update_kwargs("t", None) == {"data": "t"}
        # Nothing to change -> empty kwargs (the caller then skips the call).
        assert self._backend_with(_NewMemory())._update_kwargs(None, None) == {}


class _SyncFakeMem0Client:
    """Synchronous fake matching Mem0 2.x's client surface."""

    def __init__(self):
        self.added: list[tuple] = []
        self.updated: list[tuple] = []
        self.deleted: list[str] = []

    def search(self, query, *, top_k=20, filters=None):
        return {
            "results": [
                {
                    "id": "m1",
                    "memory": "User likes tea",
                    "score": 0.9,
                    "metadata": {"origin": "c1", "source": "conversation"},
                }
            ]
        }

    def add(self, messages, *, user_id=None, metadata=None, infer=True):
        self.added.append((messages, user_id, metadata, infer))
        return {"results": [{"id": "m2", "memory": "User likes tea", "event": "ADD"}]}

    def get_all(self, *, filters=None, top_k=20):
        return {
            "results": [
                {"id": "m1", "memory": "User likes tea", "metadata": {"origin": "c1"}}
            ]
        }

    def update(self, memory_id, text=None, metadata=None):
        self.updated.append((memory_id, text, metadata))
        return {"message": "Memory updated successfully!"}

    def delete(self, memory_id):
        self.deleted.append(memory_id)
        return {"message": "Memory deleted successfully!"}


class TestMem0BackendCrud:
    """The Mem0 backend forwards CRUD to the (fake) client, off the loop."""

    def _backend(self):
        backend = object.__new__(service_mod.Mem0Backend)
        client = _SyncFakeMem0Client()
        backend._memory = client
        backend._infer = True
        return backend, client

    async def test_search_returns_records(self):
        backend, _ = self._backend()
        records = await backend.search("tea", user_id="odin", limit=5, origin="c1")
        assert records[0]["memory"] == "User likes tea"

    async def test_add_returns_written_records(self):
        backend, client = self._backend()
        records = await backend.add(
            [{"role": "user", "content": "I like tea"}],
            user_id="odin",
            metadata={"origin": "c1"},
        )
        assert records[0]["id"] == "m2"
        assert client.added[0][2] == {"origin": "c1"}

    async def test_list_memories_returns_records(self):
        backend, _ = self._backend()
        records = await backend.list_memories(user_id="odin", limit=10)
        assert records[0]["id"] == "m1"

    async def test_update_returns_true_and_forwards(self):
        backend, client = self._backend()
        assert await backend.update("m1", text="new") is True
        assert client.updated == [("m1", "new", None)]

    async def test_update_without_changes_is_false_and_not_forwarded(self):
        backend, client = self._backend()
        assert await backend.update("m1") is False
        assert client.updated == []

    async def test_delete_returns_true_and_forwards(self):
        backend, client = self._backend()
        assert await backend.delete("m1") is True
        assert client.deleted == ["m1"]


class TestDisableThinking:
    """Reasoning models must not burn the JSON budget on hidden reasoning.

    ``_disable_thinking`` wraps Mem0's Ollama client so ``think=False`` is always
    sent. These tests use a fake client (no mem0, no network).
    """

    def test_injects_think_false_when_supported(self):
        seen = {}

        class _Client:
            def chat(self, model, messages, *, think=None, format=None, options=None):
                seen["think"] = think
                return {"message": {"content": "{}"}}

            def chat_sig_marker(self):
                pass

        class _Llm:
            client = _Client()

        class _Memory:
            llm = _Llm()

        memory = _Memory()
        _disable_thinking(memory)
        memory.llm.client.chat("m", [{"role": "user", "content": "hi"}])
        assert seen["think"] is False

    def test_explicit_think_is_respected(self):
        seen = {}

        class _Client:
            def chat(self, model, messages, *, think=None):
                seen["think"] = think
                return {}

        class _Memory:
            class llm:  # type: ignore[no-redef]
                client = _Client()

        memory = _Memory()
        _disable_thinking(memory)
        memory.llm.client.chat("m", [], think=True)
        assert seen["think"] is True

    def test_client_without_think_is_left_untouched(self):
        class _Client:
            def chat(self, model, messages):
                return "ok"

        client = _Client()
        original = client.chat

        class _Memory:
            class llm:  # type: ignore[no-redef]
                pass

        memory = _Memory()
        memory.llm.client = client
        _disable_thinking(memory)
        assert memory.llm.client.chat == original
        assert memory.llm.client.chat("m", []) == "ok"

    def test_missing_llm_is_a_noop(self):
        class _Memory:
            pass

        _disable_thinking(_Memory())  # must not raise

    def test_num_ctx_is_merged_into_options(self):
        seen = {}

        class _Client:
            def chat(self, model, messages, *, think=None, options=None):
                seen["options"] = options
                return {}

        class _Memory:
            class llm:  # type: ignore[no-redef]
                client = _Client()

        memory = _Memory()
        _disable_thinking(memory, num_ctx=16384)
        memory.llm.client.chat("m", [], options={"temperature": 0.1})
        assert seen["options"] == {"temperature": 0.1, "num_ctx": 16384}

    def test_num_ctx_does_not_override_existing_value(self):
        seen = {}

        class _Client:
            def chat(self, model, messages, *, think=None, options=None):
                seen["options"] = options
                return {}

        class _Memory:
            class llm:  # type: ignore[no-redef]
                client = _Client()

        memory = _Memory()
        _disable_thinking(memory, num_ctx=16384)
        memory.llm.client.chat("m", [], options={"num_ctx": 4096})
        assert seen["options"]["num_ctx"] == 4096


# ---------------------------------------------------------------------------
# Explicit memory tool (issue #27)
# ---------------------------------------------------------------------------
def _sample_record(**overrides) -> MemoryRecord:
    values = dict(
        id="m1",
        memory="User likes coffee",
        origin="c1",
        source=SOURCE_CONVERSATION,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-02T00:00:00+00:00",
        relevance=0.8,
        confidence=None,
    )
    values.update(overrides)
    return MemoryRecord(**values)


class TestMemoryToolContract:
    def test_definition_shape(self):
        tool = MemoryTool(_RecordingMemory())
        definition = tool.definition
        assert definition.name == "memory"
        assert definition.category == "memory"
        # Odin's own store: no approval gate.
        assert definition.requires_approval_by_default is False
        schema = definition.parameters_schema
        assert schema["required"] == ["action"]
        assert schema["properties"]["action"]["enum"] == [
            "save",
            "recall",
            "list",
            "update",
            "forget",
        ]

    def test_create_memory_tools_returns_the_tool(self):
        tools = create_memory_tools(_RecordingMemory())
        assert len(tools) == 1
        assert isinstance(tools[0], MemoryTool)

    def test_create_memory_tools_without_service_registers_nothing(self):
        # Memory off by default: the factory yields no tool, so a default
        # install keeps the exact tool surface it had before this feature.
        assert create_memory_tools(None) == []

    def test_registers_in_the_tool_registry(self):
        registry = ToolRegistry()
        for tool in create_memory_tools(_RecordingMemory()):
            registry.register(tool)
        assert registry.get("memory") is not None
        assert registry.names() == ["memory"]
        llm_tools = registry.to_llm_tools()
        assert [t.name for t in llm_tools] == ["memory"]

    def test_main_lifespan_registers_the_memory_tool(self):
        # Guards the wiring in main.py (the tool is registered next to the
        # others, sharing the service instance the agent loop receives).
        import app.main as main

        source = Path(main.__file__).read_text()
        assert "create_memory_tools(memory_service)" in source
        assert "tool_registry.register(memory_tool)" in source
        assert "memory=memory_service" in source


class TestMemoryToolActions:
    async def test_disabled_memory_reports_unavailable(self):
        tool = MemoryTool(None)
        result = await tool.execute({"action": "recall", "query": "x"}, "c1")
        assert result.success is False
        assert "disabled" in result.error.lower()

    async def test_unknown_action_is_rejected(self):
        tool = MemoryTool(_RecordingMemory())
        result = await tool.execute({"action": "explode"}, "c1")
        assert result.success is False
        assert "Unknown action" in result.error

    async def test_save_stores_the_fact_with_origin_and_source(self):
        memory = _RecordingMemory(records=[_sample_record()])
        tool = MemoryTool(memory)
        result = await tool.execute(
            {"action": "save", "text": "User likes coffee", "confidence": 0.6}, "c7"
        )
        assert result.success is True
        # origin is the running conversation; source marks an explicit tool save.
        assert memory.calls == [("remember_text", "User likes coffee", "c7", SOURCE_TOOL, 0.6)]
        assert result.output["saved"][0]["memory"] == "User likes coffee"

    async def test_save_reports_when_the_store_wrote_nothing(self):
        # Mem0's extraction may consider the fact non-durable and store nothing;
        # the tool must report count 0 rather than claim a write.
        memory = _RecordingMemory(records=[])
        tool = MemoryTool(memory)
        result = await tool.execute({"action": "save", "text": "ephemeral"}, "c1")
        assert result.success is True
        assert result.output == {"saved": [], "count": 0}

    async def test_save_requires_text(self):
        memory = _RecordingMemory()
        tool = MemoryTool(memory)
        result = await tool.execute({"action": "save"}, "c1")
        assert result.success is False
        assert memory.calls == []

    async def test_recall_returns_annotated_memories(self):
        memory = _RecordingMemory(records=[_sample_record()])
        tool = MemoryTool(memory)
        result = await tool.execute(
            {"action": "recall", "query": "coffee", "origin": "c1", "limit": 3}, "c1"
        )
        assert result.success is True
        assert memory.calls == [("recall_records", "coffee", "c1", 3)]
        record = result.output["memories"][0]
        assert record["memory"] == "User likes coffee"
        assert record["relevance"] == 0.8
        assert result.output["count"] == 1

    async def test_recall_requires_query(self):
        tool = MemoryTool(_RecordingMemory())
        result = await tool.execute({"action": "recall"}, "c1")
        assert result.success is False

    async def test_list_forwards_origin_and_limit(self):
        memory = _RecordingMemory(records=[_sample_record()])
        tool = MemoryTool(memory)
        result = await tool.execute({"action": "list", "origin": "c2", "limit": 5}, "c1")
        assert result.success is True
        assert memory.calls == [("list_memories", "c2", 5)]
        assert result.output["count"] == 1

    async def test_update_forwards_id_text_and_confidence(self):
        memory = _RecordingMemory()
        tool = MemoryTool(memory)
        result = await tool.execute(
            {"action": "update", "id": "m1", "text": "new", "confidence": 0.4}, "c1"
        )
        assert result.success is True
        assert memory.calls == [("update", "m1", "new", None, None, 0.4)]

    async def test_update_requires_something_to_change(self):
        memory = _RecordingMemory()
        tool = MemoryTool(memory)
        assert (await tool.execute({"action": "update", "id": "m1"}, "c1")).success is False
        assert (await tool.execute({"action": "update", "text": "x"}, "c1")).success is False
        assert memory.calls == []

    async def test_update_missing_memory_reports_failure(self):
        memory = _RecordingMemory()
        memory.update_result = False
        tool = MemoryTool(memory)
        result = await tool.execute({"action": "update", "id": "nope", "text": "x"}, "c1")
        assert result.success is False

    async def test_forget_forwards_id(self):
        memory = _RecordingMemory()
        tool = MemoryTool(memory)
        result = await tool.execute({"action": "forget", "id": "m1"}, "c1")
        assert result.success is True
        assert memory.calls == [("forget", "m1")]
        assert result.output["forgotten"] is True

    async def test_forget_missing_memory_reports_failure(self):
        memory = _RecordingMemory()
        memory.forget_result = False
        tool = MemoryTool(memory)
        result = await tool.execute({"action": "forget", "id": "nope"}, "c1")
        assert result.success is False


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
