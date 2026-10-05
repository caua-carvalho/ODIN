from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class SkillResponse(BaseModel):
    name: str
    description: str
    tools: list[str]
    enabled: bool
    icon: str


@router.get("", response_model=list[SkillResponse])
async def list_skills():
    from app.skills.base import skill_registry
    return [
        SkillResponse(
            name=s.name,
            description=s.description,
            tools=s.tools,
            enabled=s.enabled,
            icon=s.icon,
        )
        for s in skill_registry.all()
    ]
