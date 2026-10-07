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
from app.database.models import Conversation, Message
from app.database.session import get_db_session
from app.tools.registry import ToolRegistry

logger = logging.getLogger("odin.agent")

# Maximum messages to include in context window
MAX_CONTEXT_MESSAGES = 50


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
    ) -> None:
        self.provider = provider
        self.tool_registry = tool_registry
        self.ws_manager = websocket_manager

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

        # Build messages for LLM
        llm_messages: list[LLMMessage] = []
        for msg in history:
            llm_messages.append(self._db_message_to_llm(msg))

        llm_messages.append(LLMMessage(role="user", content=message))

        # Tool definitions for LLM
        tool_definitions = self.tool_registry.to_llm_tools()
        system_prompt = get_system_prompt()

        # Agentic loop
        full_response_text = ""
        max_iterations = 10  # prevent infinite loops

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

                elif chunk.type == "error":
                    logger.error(f"LLM error: {chunk.error}")
                    yield {"type": "error", "message": chunk.error}
                    # Save whatever we have and stop
                    if text_buffer:
                        await self._save_assistant_message(
                            conversation_id, text_buffer, []
                        )
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

                # Add tool result to context
                llm_messages.append(
                    LLMMessage(
                        role="tool",
                        content=result_content,
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
            # Update conversation title if it's the first exchange
            await self._maybe_update_title(conversation_id, message)

        yield {"type": "done", "conversation_id": conversation_id}

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
        result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
            .limit(MAX_CONTEXT_MESSAGES)
        )
        return list(result.scalars().all())

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
