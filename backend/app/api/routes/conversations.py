import uuid
from datetime import datetime, UTC
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Conversation, Message
from app.database.session import get_db
from app.api.websocket import ws_manager
from app.schemas.conversation import ConversationCreate, ConversationResponse, MessageCreate, MessageResponse

router = APIRouter()


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Conversation).order_by(Conversation.updated_at.desc()).limit(50)
    )
    return result.scalars().all()


@router.post("", response_model=ConversationResponse)
async def create_conversation(
    data: ConversationCreate, db: AsyncSession = Depends(get_db)
):
    conv = Conversation(
        id=str(uuid.uuid4()),
        title=data.title or "New Conversation",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(conversation_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.delete(conv)
    # Also delete messages
    msgs = await db.execute(
        select(Message).where(Message.conversation_id == conversation_id)
    )
    for msg in msgs.scalars().all():
        await db.delete(msg)
    await db.commit()
    return {"deleted": conversation_id}


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
async def get_messages(conversation_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return result.scalars().all()
