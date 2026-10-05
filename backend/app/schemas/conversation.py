from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ConversationCreate(BaseModel):
    title: Optional[str] = None


class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageCreate(BaseModel):
    content: str


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    tool_name: Optional[str] = None
    tool_call_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
