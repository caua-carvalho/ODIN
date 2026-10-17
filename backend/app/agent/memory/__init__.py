"""Long-term memory layer (optional, Phase 3).

Public surface:

- ``MemoryService`` — facade with full CRUD (``remember`` / ``recall`` /
  ``list_memories`` / ``update`` / ``forget``);
- ``MemoryRecord`` — a stored memory with its metadata (origin, source,
  timestamps, relevance, confidence);
- ``MemoryBackend`` — the store contract, so tests use a fake and a different
  store (e.g. sqlite-vec) can be dropped in later;
- ``create_memory_service`` — builds a Mem0-backed service from ``Settings``,
  returning ``None`` when memory is off or Mem0 is not installed.

Nothing here imports Mem0 at module level: the heavy, optional dependency is
only touched when memory is explicitly enabled (mirrors the lazy ``litellm``
import from Phase 1).
"""

from app.agent.memory.service import (
    MemoryBackend,
    MemoryRecord,
    MemoryService,
    create_memory_service,
    format_memory_context,
)

__all__ = [
    "MemoryBackend",
    "MemoryRecord",
    "MemoryService",
    "create_memory_service",
    "format_memory_context",
]
