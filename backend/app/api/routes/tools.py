from fastapi import APIRouter
from app.tools.base import ToolDefinition
from pydantic import BaseModel

router = APIRouter()


class ToolResponse(BaseModel):
    name: str
    description: str
    category: str
    requires_approval_by_default: bool
    parameters_schema: dict


@router.get("", response_model=list[ToolResponse])
async def list_tools():
    from app.main import tool_registry
    return [
        ToolResponse(
            name=t.definition.name,
            description=t.definition.description,
            category=t.definition.category,
            requires_approval_by_default=t.definition.requires_approval_by_default,
            parameters_schema=t.definition.parameters_schema,
        )
        for t in tool_registry.all()
    ]
