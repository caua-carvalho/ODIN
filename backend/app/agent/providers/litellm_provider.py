"""Unified LLM provider backed by LiteLLM.

A single adapter replaces the three hand-written ones (``gemini.py``,
``groq.py``, ``ollama.py``). LiteLLM speaks the OpenAI chat-completions shape
for every supported vendor, so one streaming + tool-call normalization works
everywhere. Vendor selection is by prefix (see ``catalog.PROVIDERS``):

    gemini/gemini-2.5-flash
    groq/llama-3.3-70b-versatile
    ollama/qwen3:0.6b
    openai/gpt-4o-mini
    anthropic/claude-3-5-sonnet-latest

Provider-specific extras that must survive a round-trip (notably Gemini thought
signatures) are carried opaquely in ``LLMToolCall.metadata`` under
``provider_specific_fields`` and re-emitted unchanged. The tool-call ``id`` is
also preserved verbatim: LiteLLM encodes the Gemini thought signature inside
that id (separator ``__thought__``) and reconstructs it on the next request, so
keeping the id intact is what makes multi-turn Gemini tool calling work — never
regenerate it for a LiteLLM provider.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import uuid
from typing import Any, AsyncIterator

from app.agent.providers.base import LLMChunk, LLMMessage, LLMTool, LLMToolCall

logger = logging.getLogger("odin.agent.providers.litellm")

# Key under which LiteLLM places provider-specific extras on a tool call
# (e.g. ``{"thought_signature": "..."}`` for Gemini).
PROVIDER_FIELDS_KEY = "provider_specific_fields"

# Settings attribute holding the API base override for providers that need one.
_API_BASE_SETTING = {
    "ollama": "ollama_base_url",
    "groq": "groq_base_url",
}

# LiteLLM is loaded lazily (see ``_get_litellm``): importing it costs ~15s, so
# it must never run at module import / app startup.
_loaded_litellm: Any | None = None


def _get_litellm() -> Any:
    """Return the LiteLLM module, importing it on first use."""
    global _loaded_litellm
    if _loaded_litellm is None:
        import litellm  # noqa: PLC0415 — intentionally lazy (heavy import)

        # Never fail a request just because a model rejects an optional param,
        # and keep LiteLLM's own banner out of the app logs.
        litellm.drop_params = True
        litellm.suppress_debug_info = True
        _loaded_litellm = litellm
    return _loaded_litellm


def warm() -> None:
    """Pre-load LiteLLM so the first request does not pay the import cost.

    Intended to be called from a background thread during app startup.
    Best-effort: a failure here must never break startup.
    """
    try:
        _get_litellm()
    except Exception as exc:  # pragma: no cover - warm-up is best effort
        logger.warning(f"Could not pre-load LiteLLM: {exc}")


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Read ``key`` from a mapping or an object attribute (both shapes occur)."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


# ---------------------------------------------------------------------------
# Transient-failure detection (rate limits / 5xx / timeouts)
# ---------------------------------------------------------------------------
# HTTP statuses worth retrying. 429 is the common one on free tiers; the 5xx
# family is the provider having a bad moment.
_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}

# Exception class names used by LiteLLM / httpx / openai for transient errors.
# Matching by name keeps this module free of a hard dependency on those packages
# (LiteLLM is imported lazily and may not even be loaded here).
_RETRYABLE_EXCEPTION_NAMES = {
    "RateLimitError",
    "Timeout",
    "TimeoutError",
    "APITimeoutError",
    "APIConnectionError",
    "ConnectionError",
    "ServiceUnavailableError",
    "InternalServerError",
}

# Last-resort substring match for providers that only expose a message.
_RETRYABLE_MESSAGE_MARKERS = (
    "rate limit",
    "rate_limit",
    "ratelimit",
    "429",
    "too many requests",
    "quota",
    "overloaded",
    "over capacity",
    "temporarily unavailable",
    "timed out",
    "timeout",
    "connection error",
    "connection reset",
    "server error",
    "bad gateway",
    "service unavailable",
    "gateway timeout",
)


def _status_code(exc: Exception) -> int | None:
    """Best-effort HTTP status extraction across provider/HTTP exception shapes."""
    for attr in ("status_code", "http_status", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    if isinstance(value, int):
        return value
    return None


def _is_retryable(exc: Exception) -> bool:
    """Whether a failed request is transient and worth reissuing."""
    if _status_code(exc) in _RETRYABLE_STATUS:
        return True
    if type(exc).__name__ in _RETRYABLE_EXCEPTION_NAMES:
        return True
    text = str(exc).lower()
    return any(marker in text for marker in _RETRYABLE_MESSAGE_MARKERS)


def _retry_after(exc: Exception) -> float | None:
    """Read a ``Retry-After`` delay (seconds) from the error, if advertised."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        headers = getattr(exc, "headers", None)
    if not headers:
        return None
    try:
        raw = headers.get("retry-after") or headers.get("Retry-After")
    except (AttributeError, TypeError):
        return None
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


def _retry_delay(
    exc: Exception, attempt: int, base_delay: float, max_delay: float
) -> float:
    """Delay before retry number ``attempt`` (1-based), honouring Retry-After.

    Falls back to exponential backoff with a little jitter so parallel clients
    do not retry in lockstep.
    """
    after = _retry_after(exc)
    if after is not None:
        return min(after, max_delay)
    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
    return delay * random.uniform(0.8, 1.2)


def _short_error(exc: Exception) -> str:
    """A terse, user-facing reason used in the retry status note."""
    status = _status_code(exc)
    if status == 429:
        return "rate limited"
    if status is not None:
        return f"HTTP {status}"
    return type(exc).__name__ or "request failed"


async def _close_stream(response: Any) -> None:
    """Close a LiteLLM stream, aborting an in-flight request. Best effort."""
    aclose = getattr(response, "aclose", None)
    if not callable(aclose):
        return
    try:
        await aclose()
    except asyncio.CancelledError:
        raise
    except Exception:  # pragma: no cover - best effort
        pass


# ---------------------------------------------------------------------------
# Internal -> LiteLLM (OpenAI chat) format
# ---------------------------------------------------------------------------
def _build_messages(messages: list[LLMMessage], system: str) -> list[dict]:
    """Convert internal messages to the OpenAI chat format LiteLLM expects."""
    out: list[dict] = []

    if system:
        out.append({"role": "system", "content": system})

    for msg in messages:
        if msg.role == "system":
            continue  # system handled above

        if msg.role == "user":
            out.append({"role": "user", "content": msg.content})

        elif msg.role == "assistant":
            content: str | None = msg.content or ""
            if msg.tool_calls and not content:
                # Providers reject an empty text part alongside tool calls.
                content = None
            entry: dict = {"role": "assistant", "content": content}
            if msg.tool_calls:
                entry["tool_calls"] = [
                    _tool_call_to_dict(tc) for tc in msg.tool_calls
                ]
            out.append(entry)

        elif msg.role == "tool":
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id or "",
                    "content": msg.content,
                }
            )

    return out


def _tool_call_to_dict(tc: LLMToolCall) -> dict:
    """Rebuild one assistant tool call, preserving LiteLLM provider extras."""
    entry: dict = {
        "id": tc.id,
        "type": "function",
        "function": {
            "name": tc.name,
            "arguments": json.dumps(tc.arguments or {}),
        },
    }
    extras = (tc.metadata or {}).get(PROVIDER_FIELDS_KEY)
    if extras:
        entry[PROVIDER_FIELDS_KEY] = extras
    return entry


def _build_tools(tools: list[LLMTool]) -> list[dict]:
    """Convert generic tool definitions to the OpenAI tool format."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters
                or {"type": "object", "properties": {}},
            },
        }
        for tool in tools
    ]


# ---------------------------------------------------------------------------
# LiteLLM (OpenAI chat) stream -> internal tool calls
# ---------------------------------------------------------------------------
def _merge_tool_call_fragment(
    states: dict[int, dict], tc_delta: Any, delta: Any = None
) -> None:
    """Accumulate one streamed tool-call delta into ``states[index]``.

    Arguments arrive in fragments; the id/name come on the first fragment. The
    id is kept verbatim (it may embed a Gemini thought signature).
    """
    index = _get(tc_delta, "index")
    if index is None:
        index = 0
    state = states.setdefault(
        index, {"id": None, "name": "", "arguments": "", PROVIDER_FIELDS_KEY: None}
    )

    tc_id = _get(tc_delta, "id")
    if tc_id:
        state["id"] = tc_id

    function = _get(tc_delta, "function")
    if function is not None:
        name = _get(function, "name")
        if name:
            state["name"] = name
        fragment = _get(function, "arguments")
        if fragment:
            state["arguments"] += fragment

    extras = _get(tc_delta, PROVIDER_FIELDS_KEY)
    if not extras and delta is not None:
        extras = _get(delta, PROVIDER_FIELDS_KEY)
    if extras:
        state[PROVIDER_FIELDS_KEY] = extras


def _finalize_tool_calls(states: dict[int, dict]) -> list[LLMChunk]:
    """Flatten accumulated tool-call deltas into complete chunks."""
    chunks: list[LLMChunk] = []
    for index in sorted(states):
        state = states[index]
        raw_args = state.get("arguments") or ""
        if raw_args:
            try:
                arguments = json.loads(raw_args)
            except json.JSONDecodeError:
                arguments = {"raw": raw_args}
        else:
            arguments = {}

        extras = state.get(PROVIDER_FIELDS_KEY)
        chunks.append(
            LLMChunk(
                type="tool_call",
                tool_call_id=state.get("id") or str(uuid.uuid4()),
                tool_name=state.get("name") or "",
                tool_arguments=arguments,
                metadata={PROVIDER_FIELDS_KEY: extras} if extras else None,
            )
        )
    return chunks


class LiteLLMProvider:
    """LLM provider that delegates to LiteLLM for every vendor."""

    def __init__(
        self,
        model: str,
        provider: str = "",
        api_key: str | None = None,
        api_base: str | None = None,
        litellm_model: str | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        retry_max_delay: float = 30.0,
    ) -> None:
        self.provider = (provider or "").strip().lower()
        self.model = model
        self.api_key = api_key or None
        self.api_base = api_base or None
        self.litellm_model = litellm_model or (
            f"{self.provider}/{model}" if self.provider else model
        )
        # Retries after the first attempt; 3 means up to 4 requests.
        self.max_retries = max(0, int(max_retries))
        self.retry_base_delay = max(0.0, float(retry_base_delay))
        self.retry_max_delay = max(0.0, float(retry_max_delay))
        logger.info(f"LiteLLMProvider initialized: {self.litellm_model}")

    @classmethod
    def from_settings(cls, config: Any, provider: str | None = None) -> "LiteLLMProvider":
        """Build a provider from ``Settings`` (or a settings-like object).

        Raises ``ValueError`` with a ``<PROVIDER>_API_KEY not configured``
        message when the selected provider needs a key that is missing.
        """
        # Imported here to avoid a circular import with the factory.
        from app.agent.providers import catalog

        name = (provider or config.odin_model_provider or "").strip().lower()
        meta = catalog.PROVIDERS.get(name)
        prefix = getattr(meta, "litellm_prefix", None) or name

        model = config.odin_model
        litellm_model = (
            model if model.startswith(f"{prefix}/") else f"{prefix}/{model}"
        )

        api_key = None
        if meta is not None and meta.api_key_setting:
            api_key = getattr(config, meta.api_key_setting, "") or ""
            if not api_key:
                raise ValueError(f"{meta.api_key_setting.upper()} not configured")

        base_setting = _API_BASE_SETTING.get(name)
        api_base = getattr(config, base_setting, "") if base_setting else None

        return cls(
            model=model,
            provider=name,
            api_key=api_key,
            api_base=api_base,
            litellm_model=litellm_model,
            max_retries=getattr(config, "odin_llm_max_retries", 3),
            retry_base_delay=getattr(config, "odin_llm_retry_base_delay", 1.0),
            retry_max_delay=getattr(config, "odin_llm_retry_max_delay", 30.0),
        )

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[LLMTool],
        system: str,
    ) -> AsyncIterator[LLMChunk]:
        """Stream a response from LiteLLM, yielding normalized chunks.

        Transient failures (rate limit, 5xx, timeout) are retried with backoff
        while nothing has been streamed yet, so a retry can never duplicate
        output. Each retry emits a ``retry`` chunk first so the UI can explain
        the wait.
        """
        litellm = _get_litellm()

        kwargs: dict[str, Any] = {
            "model": self.litellm_model,
            "messages": _build_messages(messages, system),
            "stream": True,
            "temperature": 0.7,
        }
        built_tools = _build_tools(tools)
        if built_tools:
            kwargs["tools"] = built_tools
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.api_base:
            kwargs["api_base"] = self.api_base

        attempt = 0
        while True:
            attempt += 1
            emitted = False
            tool_states: dict[int, dict] = {}
            response = None

            try:
                response = await litellm.acompletion(**kwargs)

                async for chunk in response:
                    choices = _get(chunk, "choices") or []
                    if not choices:
                        # Usage-only or empty keep-alive chunk.
                        usage = _get(chunk, "usage")
                        if usage:
                            logger.debug(f"LLM usage: {usage}")
                        continue

                    delta = _get(choices[0], "delta")
                    if delta is None:
                        continue

                    content = _get(delta, "content")
                    if content:
                        emitted = True
                        yield LLMChunk(type="text", content=content)

                    for tc_delta in _get(delta, "tool_calls") or []:
                        # Any parsed fragment makes the response non-restartable.
                        emitted = True
                        _merge_tool_call_fragment(tool_states, tc_delta, delta)

                for tool_chunk in _finalize_tool_calls(tool_states):
                    yield tool_chunk

                yield LLMChunk(type="done")
                return

            except asyncio.CancelledError:
                # The user (or the socket) aborted the turn: never retry.
                raise
            except Exception as exc:
                if (
                    not emitted
                    and attempt <= self.max_retries
                    and _is_retryable(exc)
                ):
                    # Release the failed stream before waiting.
                    if response is not None:
                        await _close_stream(response)
                        response = None
                    delay = _retry_delay(
                        exc, attempt, self.retry_base_delay, self.retry_max_delay
                    )
                    logger.warning(
                        "LiteLLM request failed (attempt %s/%s), retrying in %.1fs: %s",
                        attempt,
                        self.max_retries + 1,
                        delay,
                        exc,
                    )
                    yield LLMChunk(
                        type="retry",
                        content=(
                            f"Provider {_short_error(exc)} — "
                            f"retrying in {max(1, round(delay))}s "
                            f"({attempt}/{self.max_retries})…"
                        ),
                        retry_after=delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                logger.error(f"LiteLLM generation error: {exc}", exc_info=True)
                yield LLMChunk(type="error", error=str(exc))
                return

            finally:
                # Closing the stream aborts an in-flight request (e.g. after a
                # cancellation) and releases the upstream connection.
                if response is not None:
                    await _close_stream(response)
