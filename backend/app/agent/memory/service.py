"""Long-term memory service for the Odin agent (Phase 3).

Design
------
The agent talks to a single facade, :class:`MemoryService`, with two operations:

- ``recall(query)`` — look up memories relevant to the incoming message;
- ``remember(user, assistant)`` — persist what the exchange taught the agent.

The facade delegates to a :class:`MemoryBackend`. The default backend is Mem0
(``Mem0Backend``) configured **local-first**: the extraction LLM and the
embedder both point at the user's Ollama, and the vector store is embedded on
disk (Chroma by default) — no server, no API keys, zero marginal cost.

Why Mem0 and not sqlite-vec
---------------------------
Mem0 gives fact extraction, dedup and update for free (it runs the LLM once per
operation, which is exactly why it points at local Ollama). ``sqlite-vec`` would
be lighter — it reuses ``odin.db`` with no extra service — but the extraction /
dedup logic would have to be written by hand. The :class:`MemoryBackend` Protocol
keeps that trade-off open: a sqlite-vec backend can be dropped in without
touching the agent loop.

Everything is opt-in and lazy
-----------------------------
``mem0`` (and its vector store) is imported **only** when ``ODIN_MEMORY_ENABLED``
is true, inside :class:`Mem0Backend` (mirrors the lazy ``litellm`` import). With
memory off — the default — ``create_memory_service`` returns ``None`` and the
agent loop behaves exactly as before. If memory is enabled but the optional
package is missing or misconfigured, Odin logs a warning and boots **without**
memory: it is never mandatory on the critical path.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol, runtime_checkable

from app.config import Settings

logger = logging.getLogger("odin.memory")

# Header used when the recalled memories are injected into the system prompt.
MEMORY_CONTEXT_HEADER = (
    "Long-term memory (facts you learned in earlier conversations, for context — "
    "may be outdated; use only if relevant):"
)


@runtime_checkable
class MemoryBackend(Protocol):
    """Storage contract behind :class:`MemoryService`.

    Both methods are awaitable so the Mem0 backend can offload its blocking
    client to a thread and tests can supply a trivial async fake.
    """

    async def search(
        self, query: str, *, user_id: str = "odin", limit: int = 5
    ) -> list[dict]:  # pragma: no cover - protocol
        """Return memory records relevant to ``query`` (``[{"memory": str}, ...]``)."""
        ...

    async def add(
        self, messages: list[dict], *, user_id: str = "odin"
    ) -> None:  # pragma: no cover - protocol
        """Persist an interaction, extracting durable facts from it."""
        ...


class MemoryService:
    """Facade the agent loop uses. Never raises: recall/remember are best-effort."""

    def __init__(
        self,
        backend: MemoryBackend,
        *,
        user_id: str = "odin",
        recall_limit: int = 5,
    ) -> None:
        self._backend = backend
        self.user_id = user_id
        self.recall_limit = recall_limit

    async def recall(self, query: str, *, conversation_id: str | None = None) -> list[str]:
        """Return the memory texts relevant to ``query`` (possibly empty).

        A failure is logged and swallowed: a broken memory store must never
        take down a chat turn.
        """
        query = (query or "").strip()
        if not query:
            return []
        try:
            records = await self._backend.search(
                query, user_id=self.user_id, limit=self.recall_limit
            )
        except Exception as exc:  # noqa: BLE001 - defensive by design
            logger.warning(f"Memory recall failed (ignored): {exc}")
            return []
        return _extract_memory_texts(records)

    async def remember(
        self,
        user_message: str,
        assistant_message: str,
        *,
        conversation_id: str | None = None,
    ) -> None:
        """Persist a completed interaction for future recall (best-effort)."""
        user_message = (user_message or "").strip()
        assistant_message = (assistant_message or "").strip()
        if not user_message or not assistant_message:
            return
        messages = [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_message},
        ]
        try:
            await self._backend.add(messages, user_id=self.user_id)
        except Exception as exc:  # noqa: BLE001 - defensive by design
            logger.warning(f"Memory write-back failed (ignored): {exc}")


# ---------------------------------------------------------------------------
# Mem0 backend (lazy, local-first)
# ---------------------------------------------------------------------------
class Mem0Backend:
    """Mem0-backed store: Ollama LLM + Ollama embedder + embedded vector store.

    The ``mem0`` package is imported in ``__init__`` (not at module import), so
    it is only required when memory is enabled. Mem0's client is synchronous, so
    every call is offloaded to a thread to keep the event loop responsive.
    """

    def __init__(self, settings: Settings) -> None:
        from mem0 import Memory  # lazy, heavy, optional dependency

        config = _build_mem0_config(settings)
        logger.info(
            "Initialising Mem0 memory "
            f"(llm={settings.odin_memory_llm_model}, "
            f"embedder={settings.odin_memory_embedder_model}, "
            f"store={settings.odin_memory_vector_store})"
        )
        self._memory = Memory.from_config(config)

    async def search(
        self, query: str, *, user_id: str = "odin", limit: int = 5
    ) -> list[dict]:
        result = await asyncio.to_thread(
            self._memory.search, query, user_id=user_id, limit=limit
        )
        return _as_records(result)

    async def add(self, messages: list[dict], *, user_id: str = "odin") -> None:
        await asyncio.to_thread(self._memory.add, messages, user_id=user_id)


def _build_mem0_config(settings: Settings) -> dict:
    """Assemble the Mem0 config dict: local Ollama + embedded vector store."""
    vector_store = {
        "provider": settings.odin_memory_vector_store,
        "config": {"collection_name": "odin_memories"},
    }
    if settings.odin_memory_path:
        vector_store["config"]["path"] = settings.odin_memory_path

    return {
        "llm": {
            "provider": "ollama",
            "config": {
                "model": settings.odin_memory_llm_model,
                "ollama_base_url": settings.ollama_base_url,
            },
        },
        "embedder": {
            "provider": "ollama",
            "config": {
                "model": settings.odin_memory_embedder_model,
                "ollama_base_url": settings.ollama_base_url,
            },
        },
        "vector_store": vector_store,
    }


def create_memory_service(settings: Settings) -> MemoryService | None:
    """Build a :class:`MemoryService`, or ``None`` when memory is unavailable.

    Returns ``None`` — without raising — when:

    - ``ODIN_MEMORY_ENABLED`` is false (the default), or
    - the optional ``mem0`` package is not installed, or
    - the backend fails to initialise.

    This keeps the whole feature off the critical path: a missing dependency or
    a bad config degrades to "no memory", never to a failed startup.
    """
    if not settings.odin_memory_enabled:
        logger.info("Long-term memory disabled (ODIN_MEMORY_ENABLED=false)")
        return None

    try:
        backend: MemoryBackend = Mem0Backend(settings)
    except ImportError as exc:
        logger.warning(
            "Long-term memory is enabled but Mem0 is not installed "
            f"({exc}). Install backend/requirements-memory.txt to enable it. "
            "Continuing without memory."
        )
        return None
    except Exception as exc:  # noqa: BLE001 - never block startup
        logger.warning(
            f"Long-term memory could not be initialised ({exc}). "
            "Continuing without memory."
        )
        return None

    return MemoryService(
        backend,
        user_id=settings.odin_memory_user_id,
        recall_limit=settings.odin_memory_recall_limit,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def format_memory_context(memories: list[str]) -> str:
    """Render recalled memories as a block to append to the system prompt."""
    if not memories:
        return ""
    bullets = "\n".join(f"- {m}" for m in memories)
    return f"{MEMORY_CONTEXT_HEADER}\n{bullets}"


def _as_records(result: Any) -> list[dict]:
    """Normalise Mem0's search return value into a list of record dicts.

    Mem0 has returned both ``{"results": [...]}`` and a bare list across
    versions; accept either.
    """
    if isinstance(result, dict):
        result = result.get("results", [])
    if not isinstance(result, list):
        return []
    return [r for r in result if isinstance(r, dict)]


def _extract_memory_texts(records: list[dict]) -> list[str]:
    """Pull the human-readable text out of Mem0 records, dropping empties."""
    texts: list[str] = []
    for record in records:
        text = record.get("memory") or record.get("text") or ""
        text = str(text).strip()
        if text:
            texts.append(text)
    return texts
