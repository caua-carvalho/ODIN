from dataclasses import dataclass, field
from typing import List


@dataclass
class Skill:
    name: str
    description: str
    tools: List[str]
    enabled: bool = True
    icon: str = "🔧"


# All built-in skills
BUILTIN_SKILLS: List[Skill] = [
    Skill(
        name="Filesystem",
        description=(
            "Navigate, read, search, and organize files and directories on the system. "
            "Odin can browse your projects, read source code, search for patterns, "
            "and manage files within the workspace."
        ),
        tools=["read_file", "list_directory", "search_files", "write_file", "delete_file", "move_file", "create_directory"],
        icon="📁",
    ),
    Skill(
        name="Development",
        description=(
            "Analyze and work with software projects. Run tests, execute git commands, "
            "read and understand code, run build tools, and diagnose errors. "
            "Supports Python, Node.js, and most common development workflows."
        ),
        tools=["read_file", "list_directory", "search_files", "execute_command"],
        icon="⚙️",
    ),
    Skill(
        name="System",
        description=(
            "Query system information: CPU, memory, disk usage, running processes, "
            "network status, and system logs. Provides read-only system observability."
        ),
        tools=["execute_command", "read_file"],
        icon="🖥️",
    ),
]


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {s.name: s for s in BUILTIN_SKILLS}

    def all(self) -> List[Skill]:
        return list(self._skills.values())

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def enable(self, name: str) -> bool:
        skill = self._skills.get(name)
        if skill:
            skill.enabled = True
            return True
        return False

    def disable(self, name: str) -> bool:
        skill = self._skills.get(name)
        if skill:
            skill.enabled = False
            return True
        return False


skill_registry = SkillRegistry()
