"""Long-term memory service for the Odin agent (Phase 3).

Design
------
The agent talks to a single facade, :class:`MemoryService`, which exposes the
full CRUD surface the issue asks for:

- ``remember`` / ``remember_text`` — create (persist an exchange or a fact);
- ``recall`` / ``recall_records`` / ``list_memories`` — read (semantic search
  and plain listing);
- ``update`` — change a memory's text and/or its metadata;
- ``forget`` — delete a memory by id.

Every method is *best-effort*: failures are logged and swallowed (returning an
empty/`False` result) so a broken store can never take down a chat turn.

Each memory carries metadata: ``origin`` (e.g. the ``conversation_id`` it came
from), ``source`` (``conversation`` / ``tool`` / ``briefing``), a ``created_at``
timestamp, an optional ``confidence`` and — on search — the backend's
``relevance`` score. Honesty over completeness: Mem0 exposes no confidence
signal, so ``confidence`` is ``None`` unless the caller supplies one; it is
never fabricated.

The facade delegates to a :class:`MemoryBackend`. The default backend is Mem0
(``Mem0Backend``) configured **local-first**: the extraction LLM and the
embedder both point at the user's Ollama, and the vector store is embedded on
disk (Chroma by default) — no server, no API keys, zero marginal cost.

Two escape hatches exist for machines where the extraction LLM is a problem
(Mem0's V3 prompt is ~7.4k tokens):

- ``ODIN_MEMORY_LLM_PROVIDER`` can point the extraction LLM at a hosted
  provider (``groq``/``openai``/``anthropic``/``gemini``); the embedder stays
  local;
- ``ODIN_MEMORY_INFER=false`` skips extraction entirely — Mem0 then stores the
  raw turns and recall is pure embedding similarity (fully offline, instant).

Why Mem0 and not sqlite-vec
---------------------------
Mem0 gives fact extraction, dedup, update and delete for free (it runs the LLM
once per write, which is exactly why it points at local Ollama). ``sqlite-vec``
would be lighter — it reuses ``odin.db`` with no extra service — but the
extraction / dedup logic would have to be written by hand, and the issue's
"tabela SQLite criada no startup" criterion is knowingly traded for that.
The :class:`MemoryBackend` Protocol keeps the trade-off open: a sqlite-vec
backend can be dropped in without touching the agent loop or the tool.

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
import inspect
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from app.config import Settings

logger = logging.getLogger("odin.memory")

# Header used when the recalled memories are injected into the system prompt.
MEMORY_CONTEXT_HEADER = (
    "Long-term memory (facts you learned in earlier conversations, for context — "
    "may be outdated; use only if relevant):"
)

# How a memory was created, recorded in its metadata (the issue's
# "origem: conversa / ferramenta / briefing").
SOURCE_CONVERSATION = "conversation"
SOURCE_TOOL = "tool"
SOURCE_BRIEFING = "briefing"


@dataclass
class MemoryRecord:
    """A single stored memory plus the metadata the issue asks for.

    Attributes
    ----------
    memory:
        The fact text.
    origin:
        Where it came from — the ``conversation_id`` for automatic captures.
    source:
        The kind of origin (``conversation`` / ``tool`` / ``briefing``).
    created_at / updated_at:
        ISO-8601 timestamps. Read from the backend's own fields when it exposes
        them, otherwise from the metadata written at store time.
    relevance:
        The backend's similarity score for a search hit; ``None`` when listing.
    confidence:
        How sure the store is that the fact is correct. Mem0 exposes **no**
        confidence signal, so this is ``None`` unless a caller stored one — it
        is never fabricated.
    metadata:
        The raw metadata dict as returned by the backend.
    """

    memory: str
    id: str | None = None
    origin: str | None = None
    source: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    relevance: float | None = None
    confidence: float | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """JSON-serialisable view (used by the memory tool)."""
        return {
            "id": self.id,
            "memory": self.memory,
            "origin": self.origin,
            "source": self.source,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "relevance": self.relevance,
            "confidence": self.confidence,
        }


@runtime_checkable
class MemoryBackend(Protocol):
    """Storage contract behind :class:`MemoryService`.

    Every method is awaitable so the Mem0 backend can offload its blocking
    client to a thread and tests can supply a trivial async fake. Each returns
    plain record dicts (or ``bool`` for mutations); mapping them to
    :class:`MemoryRecord` happens once, in the facade.
    """

    async def search(
        self,
        query: str,
        *,
        user_id: str = "odin",
        limit: int = 5,
        origin: str | None = None,
    ) -> list[dict]:  # pragma: no cover - protocol
        """Return memory records relevant to ``query`` (``[{"memory": str}, ...]``)."""
        ...

    async def add(
        self,
        messages: list[dict],
        *,
        user_id: str = "odin",
        metadata: dict | None = None,
    ) -> list[dict]:  # pragma: no cover - protocol
        """Persist an interaction, extracting durable facts from it.

        Returns the affected records (may be empty) so the caller can report ids.
        """
        ...

    async def list_memories(
        self,
        *,
        user_id: str = "odin",
        limit: int = 100,
        origin: str | None = None,
    ) -> list[dict]:  # pragma: no cover - protocol
        """Return every stored memory for the user (newest/relevance order)."""
        ...

    async def update(
        self,
        memory_id: str,
        *,
        text: str | None = None,
        metadata: dict | None = None,
    ) -> bool:  # pragma: no cover - protocol
        """Update a memory's text and/or metadata. ``True`` on success."""
        ...

    async def delete(
        self, memory_id: str
    ) -> bool:  # pragma: no cover - protocol
        """Forget (delete) a memory by id. ``True`` on success."""
        ...


class MemoryService:
    """Facade the agent and the memory tool use. Never raises: best-effort CRUD."""

    def __init__(
        self,
        backend: MemoryBackend,
        *,
        user_id: str = "odin",
        recall_limit: int = 5,
        list_limit: int = 100,
        store_metadata: bool = True,
    ) -> None:
        self._backend = backend
        self.user_id = user_id
        self.recall_limit = recall_limit
        # Cap for explicit listings (the tool's `list` action). Bounds what the
        # agent can pull into its context at once.
        self.list_limit = list_limit
        # When false, memories are stored without the origin/source/timestamp
        # metadata (escape hatch for stores that reject custom metadata).
        self.store_metadata = store_metadata

    # -- read ---------------------------------------------------------------
    async def recall(
        self,
        query: str,
        *,
        conversation_id: str | None = None,
        origin: str | None = None,
        limit: int | None = None,
    ) -> list[str]:
        """Return the memory texts relevant to ``query`` (possibly empty).

        ``origin`` optionally narrows the search to memories from one source
        (e.g. a ``conversation_id``). ``conversation_id`` is accepted for
        signature compatibility with the agent loop and is **not** used as a
        filter — long-term memory is deliberately cross-conversation.

        A failure is logged and swallowed: a broken memory store must never
        take down a chat turn.
        """
        records = await self._search(query, limit=limit, origin=origin)
        return _extract_memory_texts(records)

    async def recall_records(
        self,
        query: str,
        *,
        origin: str | None = None,
        limit: int | None = None,
    ) -> list[MemoryRecord]:
        """Like :meth:`recall`, but return annotated :class:`MemoryRecord`s.

        Search hits carry their ``relevance`` score and their stored metadata;
        a failure yields an empty list.
        """
        records = await self._search(query, limit=limit, origin=origin)
        return _to_records(records, relevance_key="score")

    async def list_memories(
        self, *, origin: str | None = None, limit: int | None = None
    ) -> list[MemoryRecord]:
        """Return stored memories (no query), newest/backend order, annotated."""
        try:
            records = await self._backend.list_memories(
                user_id=self.user_id,
                limit=limit or self.list_limit,
                origin=origin,
            )
        except Exception as exc:  # noqa: BLE001 - defensive by design
            logger.warning(f"Memory listing failed (ignored): {exc}")
            return []
        return _to_records(records)

    # -- write --------------------------------------------------------------
    async def remember(
        self,
        user_message: str,
        assistant_message: str,
        *,
        conversation_id: str | None = None,
        source: str = SOURCE_CONVERSATION,
        confidence: float | None = None,
    ) -> list[MemoryRecord]:
        """Persist a completed interaction for future recall (best-effort).

        ``conversation_id`` is stored as the memory's ``origin``. Returns the
        records the backend reports as written (may be empty).
        """
        user_message = (user_message or "").strip()
        assistant_message = (assistant_message or "").strip()
        if not user_message or not assistant_message:
            return []
        messages = [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_message},
        ]
        return await self._write(
            messages, origin=conversation_id, source=source, confidence=confidence
        )

    async def remember_text(
        self,
        text: str,
        *,
        origin: str | None = None,
        source: str = SOURCE_TOOL,
        confidence: float | None = None,
    ) -> list[MemoryRecord]:
        """Persist a single explicit fact (the tool's ``save`` action)."""
        text = (text or "").strip()
        if not text:
            return []
        return await self._write(
            [{"role": "user", "content": text}],
            origin=origin,
            source=source,
            confidence=confidence,
        )

    async def update(
        self,
        memory_id: str,
        *,
        text: str | None = None,
        origin: str | None = None,
        source: str | None = None,
        confidence: float | None = None,
    ) -> bool:
        """Update a memory's text and/or metadata. ``False`` on any failure."""
        memory_id = (memory_id or "").strip()
        if not memory_id:
            return False
        new_text = text.strip() if isinstance(text, str) else None
        metadata: dict | None = None
        has_metadata_change = (
            origin is not None or source is not None or confidence is not None
        )
        if self.store_metadata and has_metadata_change:
            metadata = {"updated_at": _now_iso()}
            if origin is not None:
                metadata["origin"] = str(origin)
            if source is not None:
                metadata["source"] = str(source)
            if confidence is not None:
                metadata["confidence"] = _as_float(confidence)
        if not new_text and not metadata:
            return False
        try:
            return bool(
                await self._backend.update(
                    memory_id, text=new_text, metadata=metadata
                )
            )
        except Exception as exc:  # noqa: BLE001 - defensive by design
            logger.warning(f"Memory update failed (ignored): {exc}")
            return False

    async def forget(self, memory_id: str) -> bool:
        """Delete a memory by id. ``False`` on any failure."""
        memory_id = (memory_id or "").strip()
        if not memory_id:
            return False
        try:
            return bool(await self._backend.delete(memory_id))
        except Exception as exc:  # noqa: BLE001 - defensive by design
            logger.warning(f"Memory forget failed (ignored): {exc}")
            return False

    # -- internals ----------------------------------------------------------
    async def _search(
        self, query: str, *, limit: int | None, origin: str | None
    ) -> list[dict]:
        query = (query or "").strip()
        if not query:
            return []
        try:
            return await self._backend.search(
                query,
                user_id=self.user_id,
                limit=limit or self.recall_limit,
                origin=origin,
            )
        except Exception as exc:  # noqa: BLE001 - defensive by design
            logger.warning(f"Memory recall failed (ignored): {exc}")
            return []

    async def _write(
        self,
        messages: list[dict],
        *,
        origin: str | None,
        source: str,
        confidence: float | None,
    ) -> list[MemoryRecord]:
        metadata = (
            _build_memory_metadata(origin=origin, source=source, confidence=confidence)
            if self.store_metadata
            else None
        )
        try:
            records = await self._backend.add(
                messages, user_id=self.user_id, metadata=metadata
            )
        except Exception as exc:  # noqa: BLE001 - defensive by design
            logger.warning(f"Memory write-back failed (ignored): {exc}")
            return []
        return _to_records(records)


# ---------------------------------------------------------------------------
# Mem0 backend (lazy, local-first)
# ---------------------------------------------------------------------------
class Mem0Backend:
    """Mem0-backed store: Ollama LLM + Ollama embedder + embedded vector store.

    The ``mem0`` package is imported in ``__init__`` (not at module import), so
    it is only required when memory is enabled. Mem0's client is synchronous, so
    every call is offloaded to a thread to keep the event loop responsive.
    """

    # Whether Mem0 runs its extraction LLM on write. Overridden from settings;
    # the class default keeps ``object.__new__`` test doubles working.
    _infer: bool = True

    def __init__(self, settings: Settings) -> None:
        from mem0 import Memory  # lazy, heavy, optional dependency

        config = _build_mem0_config(settings)
        logger.info(
            "Initialising Mem0 memory "
            f"(llm={settings.odin_memory_llm_provider}:{settings.odin_memory_llm_model}, "
            f"embedder={settings.odin_memory_embedder_model}, "
            f"store={settings.odin_memory_vector_store})"
        )
        self._memory = Memory.from_config(config)
        self._infer = settings.odin_memory_infer
        if (settings.odin_memory_llm_provider or "ollama").strip().lower() == "ollama":
            _disable_thinking(self._memory, num_ctx=settings.odin_memory_num_ctx)

    async def search(
        self,
        query: str,
        *,
        user_id: str = "odin",
        limit: int = 5,
        origin: str | None = None,
    ) -> list[dict]:
        kwargs = self._search_kwargs(user_id, limit, origin)
        result = await asyncio.to_thread(self._memory.search, query, **kwargs)
        return _as_records(result)

    async def add(
        self,
        messages: list[dict],
        *,
        user_id: str = "odin",
        metadata: dict | None = None,
    ) -> list[dict]:
        kwargs = self._add_kwargs(user_id, metadata)
        result = await asyncio.to_thread(self._memory.add, messages, **kwargs)
        return _as_records(result)

    async def list_memories(
        self,
        *,
        user_id: str = "odin",
        limit: int = 100,
        origin: str | None = None,
    ) -> list[dict]:
        kwargs = self._list_kwargs(user_id, limit, origin)
        result = await asyncio.to_thread(self._memory.get_all, **kwargs)
        return _as_records(result)

    async def update(
        self,
        memory_id: str,
        *,
        text: str | None = None,
        metadata: dict | None = None,
    ) -> bool:
        kwargs = self._update_kwargs(text, metadata)
        if not kwargs:
            return False
        await asyncio.to_thread(self._memory.update, memory_id, **kwargs)
        return True

    async def delete(self, memory_id: str) -> bool:
        await asyncio.to_thread(self._memory.delete, memory_id)
        return True

    def _search_kwargs(
        self, user_id: str, limit: int, origin: str | None = None
    ) -> dict:
        """Build search kwargs for the installed Mem0's API.

        Mem0 2.x moved the entity to ``filters={"user_id": ...}`` and renamed the
        result cap to ``top_k``; older versions take ``user_id``/``limit`` as
        top-level kwargs. Introspect once and adapt (the extra kwargs land in
        ``**kwargs`` on 2.x and would otherwise be silently ignored).

        ``origin`` is an extra metadata filter and is only supported on the
        literal-``filters`` API (2.x); legacy versions ignore it.
        """
        params = inspect.signature(self._memory.search).parameters
        if "filters" in params:
            filters: dict = {"user_id": user_id}
            if origin:
                filters["origin"] = origin
            return {"filters": filters, "top_k": limit}
        return {"user_id": user_id, "limit": limit}

    def _add_kwargs(self, user_id: str, metadata: dict | None = None) -> dict:
        params = inspect.signature(self._memory.add).parameters
        if "user_id" in params:
            kwargs: dict = {"user_id": user_id}
        else:
            kwargs = {"filters": {"user_id": user_id}}
        if "infer" in params:
            kwargs["infer"] = self._infer
        if metadata and "metadata" in params:
            kwargs["metadata"] = metadata
        return kwargs

    def _list_kwargs(
        self, user_id: str, limit: int, origin: str | None = None
    ) -> dict:
        """Build ``get_all`` kwargs, adapting to the installed Mem0 API.

        Mirrors :meth:`_search_kwargs`: 2.x takes ``filters``/``top_k``, older
        versions take ``user_id``/``limit``.
        """
        params = inspect.signature(self._memory.get_all).parameters
        if "filters" in params:
            filters: dict = {"user_id": user_id}
            if origin:
                filters["origin"] = origin
            return {"filters": filters, "top_k": limit}
        return {"user_id": user_id, "limit": limit}

    def _update_kwargs(self, text: str | None, metadata: dict | None) -> dict:
        """Build ``update`` kwargs, adapting to the installed Mem0 API.

        Mem0 2.x renamed ``data`` to ``text``; the legacy name is still accepted
        here so older installs keep working.
        """
        params = inspect.signature(self._memory.update).parameters
        kwargs: dict = {}
        if text is not None:
            if "text" in params:
                kwargs["text"] = text
            elif "data" in params:
                kwargs["data"] = text
        if metadata and "metadata" in params:
            kwargs["metadata"] = metadata
        return kwargs


def _disable_thinking(memory: Any, *, num_ctx: int | None = None) -> None:
    """Configure Mem0's Ollama LLM for reliable, fast structured extraction.

    Mem0's ``OllamaLLM.generate_response`` passes neither Ollama's ``think`` flag
    nor a ``num_ctx``. Two problems follow:

    - Reasoning models (e.g. ``qwen3``) spend the whole ``num_predict`` budget on
      hidden reasoning and never emit the JSON contract Mem0 parses — extraction
      comes back empty and **nothing is stored, silently**.
    - Mem0's V3 extraction prompt is ~34k chars (~8.5k tokens), far beyond
      Ollama's default 4096-token context; the prompt is truncated and the model
      extracts nothing.

    This wrapper forces ``think=False`` and raises ``num_ctx`` when the installed
    ``ollama`` client supports them (older clients are left untouched).
    """
    client = getattr(getattr(memory, "llm", None), "client", None)
    chat = getattr(client, "chat", None)
    if chat is None:
        return
    try:
        params = inspect.signature(chat).parameters
    except (TypeError, ValueError):
        return
    supports_think = "think" in params
    if not supports_think and num_ctx is None:
        return

    def chat_configured(*args: Any, **kwargs: Any) -> Any:
        if supports_think:
            kwargs.setdefault("think", False)
        if num_ctx is not None:
            options = dict(kwargs.get("options") or {})
            options.setdefault("num_ctx", num_ctx)
            kwargs["options"] = options
        return chat(*args, **kwargs)

    client.chat = chat_configured


def _build_mem0_config(settings: Settings) -> dict:
    """Assemble the Mem0 config dict: extraction LLM + embedded vector store.

    The embedder is always the local Ollama embedder (fast on CPU, no API key).
    The extraction LLM defaults to local Ollama but any Mem0 provider can be
    selected via ``ODIN_MEMORY_LLM_PROVIDER`` — the matching ``*_API_KEY``
    setting is picked up automatically.
    """
    vector_store = {
        "provider": settings.odin_memory_vector_store,
        "config": {"collection_name": "odin_memories"},
    }
    if settings.odin_memory_path:
        vector_store["config"]["path"] = settings.odin_memory_path

    return {
        "llm": _build_llm_config(settings),
        "embedder": {
            "provider": "ollama",
            "config": {
                "model": settings.odin_memory_embedder_model,
                "ollama_base_url": settings.ollama_base_url,
            },
        },
        "vector_store": vector_store,
    }


# Mem0 LLM provider -> the Settings field holding its API key.
_MEMORY_API_KEY_FIELDS = {
    "groq": "groq_api_key",
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "gemini": "gemini_api_key",
}


def _build_llm_config(settings: Settings) -> dict:
    """Build Mem0's ``llm`` config for the configured provider."""
    provider = (settings.odin_memory_llm_provider or "ollama").strip().lower()
    if provider == "ollama":
        return {
            "provider": "ollama",
            "config": {
                "model": settings.odin_memory_llm_model,
                "ollama_base_url": settings.ollama_base_url,
                "max_tokens": settings.odin_memory_llm_max_tokens,
            },
        }

    config: dict[str, Any] = {
        "model": settings.odin_memory_llm_model,
        "max_tokens": settings.odin_memory_llm_max_tokens,
    }
    key_field = _MEMORY_API_KEY_FIELDS.get(provider)
    if key_field:
        api_key = getattr(settings, key_field, "")
        if api_key:
            config["api_key"] = api_key
    return {"provider": provider, "config": config}


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
        list_limit=settings.odin_memory_list_limit,
        store_metadata=settings.odin_memory_store_metadata,
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


def _now_iso() -> str:
    """Current UTC timestamp as an ISO-8601 string (timezone-aware)."""
    return datetime.now(UTC).isoformat()


def _build_memory_metadata(
    *,
    origin: str | None,
    source: str,
    confidence: float | None = None,
) -> dict:
    """Assemble the metadata stored with a memory.

    Only honest values are written: ``origin``/``source`` are known by
    construction, ``created_at`` is the real write time, and ``confidence`` is
    omitted unless a caller supplied one (Mem0 has no confidence signal of its
    own, so inventing a number would be misleading).
    """
    metadata: dict = {
        "origin": str(origin) if origin else "unknown",
        "source": str(source) if source else SOURCE_CONVERSATION,
        "created_at": _now_iso(),
    }
    if confidence is not None:
        metadata["confidence"] = _as_float(confidence)
    return metadata


def _as_float(value: Any) -> float | None:
    """Coerce a metadata value to ``float``, or ``None`` when it is not numeric."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_records(result: Any) -> list[dict]:
    """Normalise Mem0's return value into a list of record dicts.

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


def _to_records(
    raw: list[dict], *, relevance_key: str | None = None
) -> list[MemoryRecord]:
    """Map backend record dicts to :class:`MemoryRecord`s (dropping textless ones).

    ``relevance_key`` names the field carrying the similarity score (``score``
    for a Mem0 search); a plain listing passes ``None`` and leaves relevance
    unset. Metadata is the single source for origin/source/confidence, with the
    backend's own top-level fields winning for timestamps when present.
    """
    records: list[MemoryRecord] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = item.get("memory") or item.get("text") or ""
        text = str(text).strip()
        if not text:
            continue
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        records.append(
            MemoryRecord(
                memory=text,
                id=_as_str(item.get("id")),
                origin=_as_str(item.get("origin") or metadata.get("origin")),
                source=_as_str(item.get("source") or metadata.get("source")),
                created_at=_as_str(
                    item.get("created_at") or metadata.get("created_at")
                ),
                updated_at=_as_str(
                    item.get("updated_at") or metadata.get("updated_at")
                ),
                relevance=_as_float(item.get(relevance_key)) if relevance_key else None,
                confidence=_as_float(
                    item.get("confidence", metadata.get("confidence"))
                ),
                metadata=metadata,
            )
        )
    return records


def _as_str(value: Any) -> str | None:
    """Coerce a value to ``str``, mapping ``None``/empty to ``None``."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None
