import asyncio
import json
import logging
import uuid
from datetime import datetime, UTC
from typing import AsyncIterator, Callable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError

from app.agent.providers.base import LLMMessage, LLMChunk, LLMToolCall
from app.agent.prompts.system import get_system_prompt
from app.agent.memory import format_memory_context
from app.database.models import Conversation, Message
from app.database.session import get_db_session
from app.tools.registry import ToolRegistry

logger = logging.getLogger("odin.agent")

# Maximum messages to include in context window
MAX_CONTEXT_MESSAGES = 50

# Tool results can be huge (a whole file or directory listing). Truncate what we
# feed back into the LLM context so a single tool call cannot blow the context
# window; the UI still receives the full result in the `tool_end` event.
MAX_TOOL_RESULT_CHARS = 8000


def _truncate_for_context(content: str, limit: int = MAX_TOOL_RESULT_CHARS) -> str:
    """Bound a tool result fed back to the LLM, keeping the head of the payload.

    Returns ``content`` unchanged when it already fits; otherwise truncates and
    appends a marker so the model knows the view is partial.
    """
    if content is None or len(content) <= limit:
        return content
    removed = len(content) - limit
    return f"{content[:limit]}\n…[truncated {removed} chars]"


class OdinAgent:
    """The core Odin agent.

    Manages the agentic loop: receive user message → call LLM → execute tools
    → feed results back → repeat until done.
    """

    def __init__(
        self,
        provider,  # LLMProvider
        tool_registry: ToolRegistry,
        websocket_manager=None,
        memory=None,  # Optional[MemoryService]
    ) -> None:
        self.provider = provider
        self.tool_registry = tool_registry
        self.ws_manager = websocket_manager
        # Optional long-term memory (Phase 3). ``None`` (the default) means the
        # loop is byte-for-byte the same as before this feature existed.
        self.memory = memory

    async def chat(
        self,
        message: str,
        conversation_id: str,
        on_event: Optional[Callable] = None,
    ) -> AsyncIterator[dict]:
        """
        Process a user message and yield events for streaming.

        Events yielded:
        - {type: 'status', message: '...'}
        - {type: 'text_chunk', content: '...'}
        - {type: 'tool_start', tool: '...', arguments: {...}}
        - {type: 'tool_end', tool: '...', result: {...}, success: bool}
        - {type: 'permission_request', id: '...', ...}
        - {type: 'done', conversation_id: '...'}
        - {type: 'error', message: '...'}
        """
        yield {"type": "status", "message": "Thinking..."}

        # Load or create conversation
        async with get_db_session() as db:
            await self._ensure_conversation(db, conversation_id)

            # Load history
            history = await self._load_history(db, conversation_id)

            # Save user message
            user_msg = Message(
                id=str(uuid.uuid4()),
                conversation_id=conversation_id,
                role="user",
                content=message,
                created_at=datetime.now(UTC),
            )
            db.add(user_msg)

        # Recall long-term memories before constructing the context. Memories are
        # appended to the system prompt (do not add them as messages) so that the
        # LiteLLM adapter — which moves system-only instructions to the top-level
        # "system" field — carries them to the provider unchanged.
        system_prompt = get_system_prompt()
        if self.memory is not None:
            memories = await self.memory.recall(message, conversation_id=conversation_id)
            if memories:
                system_prompt = system_prompt + "\n\n" + format_memory_context(memories)

        # Build messages for LLM
        llm_messages: list[LLMMessage] = []
        for msg in history:
            llm_messages.append(self._db_message_to_llm(msg))

        llm_messages.append(LLMMessage(role="user", content=message))

        # Tool definitions for LLM
        tool_definitions = self.tool_registry.to_llm_tools()

        # Agentic loop
        full_response_text = ""
        text_buffer = ""
        max_iterations = 10  # prevent infinite loops
        saved = False

        try:
            for iteration in range(max_iterations):
                logger.info(f"Agent iteration {iteration + 1} for conversation {conversation_id}")

                text_buffer = ""
                tool_calls_this_turn: list[LLMToolCall] = []

                async for chunk in self.provider.generate(
                    messages=llm_messages,
                    tools=tool_definitions,
                    system=system_prompt,
                ):
                    if chunk.type == "text":
                        text_buffer += chunk.content or ""
                        yield {"type": "text_chunk", "content": chunk.content}

                    elif chunk.type == "tool_call":
                        tool_calls_this_turn.append(
                            LLMToolCall(
                                id=chunk.tool_call_id or str(uuid.uuid4()),
                                name=chunk.tool_name or "",
                                arguments=chunk.tool_arguments or {},
                                metadata=chunk.metadata,
                            )
                        )

                    elif chunk.type == "retry":
                        # Transient provider failure (e.g. a 429 on a free tier)
                        # is being retried by the provider; keep the user posted.
                        yield {
                            "type": "status",
                            "message": chunk.content or "Retrying…",
                        }

                    elif chunk.type == "error":
                        logger.error(f"LLM error: {chunk.error}")
                        yield {"type": "error", "message": chunk.error}
                        return

                    elif chunk.type == "done":
                        break

                # Add assistant response to context
                if text_buffer or tool_calls_this_turn:
                    llm_messages.append(
                        LLMMessage(
                            role="assistant",
                            content=text_buffer,
                            tool_calls=tool_calls_this_turn if tool_calls_this_turn else None,
                        )
                    )
                    full_response_text += text_buffer
                    # Reset so the abort handler below never double-counts this
                    # turn if the turn is cancelled during tool execution.
                    text_buffer = ""

                # No tool calls → we're done
                if not tool_calls_this_turn:
                    break

                # Execute tool calls
                for tc in tool_calls_this_turn:
                    tool_name = tc.name
                    tool_args = tc.arguments
                    call_id = tc.id

                    logger.info(f"Tool call: {tool_name}({json.dumps(tool_args)[:100]})")

                    yield {
                        "type": "tool_start",
                        "tool": tool_name,
                        "tool_call_id": call_id,
                        "arguments": tool_args,
                    }

                    tool = self.tool_registry.get(tool_name)
                    if not tool:
                        result_content = json.dumps(
                            {"error": f"Unknown tool: {tool_name}"}
                        )
                        yield {
                            "type": "tool_end",
                            "tool": tool_name,
                            "tool_call_id": call_id,
                            "success": False,
                            "result": {"error": f"Unknown tool: {tool_name}"},
                        }
                    else:
                        try:
                            result = await tool.execute(tool_args, conversation_id)

                            if result.requires_approval and not result.success:
                                yield {
                                    "type": "status",
                                    "message": "Waiting for authorization...",
                                }

                            result_dict = result.model_dump()
                            result_content = json.dumps(result_dict)

                            yield {
                                "type": "tool_end",
                                "tool": tool_name,
                                "tool_call_id": call_id,
                                "success": result.success,
                                "result": result_dict,
                            }

                        except Exception as e:
                            logger.error(f"Tool {tool_name} raised exception: {e}", exc_info=True)
                            result_content = json.dumps({"error": str(e)})
                            yield {
                                "type": "tool_end",
                                "tool": tool_name,
                                "tool_call_id": call_id,
                                "success": False,
                                "result": {"error": str(e)},
                            }

                    # Add tool result to context (truncated: the event above
                    # carries the full result to the UI; the LLM only needs
                    # a bounded view).
                    llm_messages.append(
                        LLMMessage(
                            role="tool",
                            content=_truncate_for_context(result_content),
                            tool_call_id=call_id,
                            tool_name=tool_name,
                        )
                    )

                    yield {"type": "status", "message": "Thinking..."}

            # Save final assistant message to DB
            if full_response_text:
                await self._save_assistant_message(
                    conversation_id, full_response_text, []
                )
                saved = True
                # Update conversation title if it's the first exchange
                await self._maybe_update_title(conversation_id, message)

            yield {"type": "done", "conversation_id": conversation_id}

        finally:
            # Persist whatever streamed when the turn is aborted — the user
            # pressed "stop", the socket dropped, or the app is shutting down —
            # so history matches the transcript the client already saw.
            if not saved:
                partial = f"{full_response_text}{text_buffer}".strip()
                if partial:
                    try:
                        await self._save_assistant_message(
                            conversation_id, partial, []
                        )
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:  # pragma: no cover - best effort
                        logger.warning(
                            f"Could not persist partial assistant message: {exc}"
                        )

        # Persist the exchange to long-term memory AFTER `done`: Mem0 runs an
        # extraction LLM call, so doing it here keeps it off the completion
        # signal's critical path. Best-effort — `remember` never raises.
        if self.memory is not None and full_response_text:
            await self.memory.remember(
                user_message=message,
                assistant_message=full_response_text,
                conversation_id=conversation_id,
            )

    async def _ensure_conversation(self, db: AsyncSession, conversation_id: str) -> None:
        result = await db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if not conv:
            conv = Conversation(
                id=conversation_id,
                title="New Conversation",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db.add(conv)

    async def _load_history(self, db: AsyncSession, conversation_id: str) -> list[Message]:
        """Load the most recent messages, in chronological (oldest-first) order.

        Ordered DESC (newest first) then reversed: the previous ASC query
        returned the *oldest* MAX_CONTEXT_MESSAGES, so in long conversations the
        agent forgot the tail of the thread.
        """
        result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(MAX_CONTEXT_MESSAGES)
        )
        # Newest-first window -> restore chronological order for the LLM.
        return list(reversed(result.scalars().all()))

    def _db_message_to_llm(self, msg: Message) -> LLMMessage:
        tool_calls = None
        if msg.metadata_json:
            try:
                meta = json.loads(msg.metadata_json)
                raw_calls = meta.get("tool_calls")
                if raw_calls:
                    tool_calls = [LLMToolCall.model_validate(tc) for tc in raw_calls]
            except (json.JSONDecodeError, AttributeError, TypeError, ValidationError):
                tool_calls = None

        return LLMMessage(
            role=msg.role,
            content=msg.content or "",
            tool_calls=tool_calls,
            tool_call_id=msg.tool_call_id,
            tool_name=msg.tool_name,
        )

    async def _save_assistant_message(
        self,
        conversation_id: str,
        content: str,
        tool_calls: list[dict],
    ) -> None:
        async with get_db_session() as db:
            msg = Message(
                id=str(uuid.uuid4()),
                conversation_id=conversation_id,
                role="assistant",
                content=content,
                metadata_json=json.dumps({"tool_calls": tool_calls}) if tool_calls else None,
                created_at=datetime.now(UTC),
            )
            db.add(msg)

            # Update conversation timestamp
            result = await db.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conv = result.scalar_one_or_none()
            if conv:
                conv.updated_at = datetime.now(UTC)

    async def _maybe_update_title(self, conversation_id: str, first_message: str) -> None:
        """Set conversation title from the first user message."""
        async with get_db_session() as db:
            result = await db.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conv = result.scalar_one_or_none()
            if conv and conv.title == "New Conversation":
                title = first_message[:60].strip()
                if len(first_message) > 60:
                    title += "..."
                conv.title = title
