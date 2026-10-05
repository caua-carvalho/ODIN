from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class PermissionResponse(BaseModel):
    id: str
    conversation_id: str
    tool: str
    operation: str
    arguments_json: str
    target: str
    reason: str
    risk_level: str
    status: str
    created_at: datetime
    resolved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PermissionListResponse(BaseModel):
    items: list[PermissionResponse]
    total: int
