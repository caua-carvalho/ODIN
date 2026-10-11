"""LLM provider layer.

The rest of the application depends only on the contracts in `base` and
the `create_llm_provider` factory. Concrete providers are imported lazily
by the factory.
"""

from app.agent.providers import catalog
from app.agent.providers.base import (
    LLMChunk,
    LLMMessage,
    LLMProvider,
    LLMTool,
    LLMToolCall,
)
from app.agent.providers.factory import create_llm_provider

__all__ = [
    "LLMChunk",
    "LLMMessage",
    "LLMProvider",
    "LLMTool",
    "LLMToolCall",
    "catalog",
    "create_llm_provider",
]
