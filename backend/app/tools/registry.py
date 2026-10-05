import logging
from typing import Dict, List, Optional

from app.tools.base import BaseTool, ToolDefinition

logger = logging.getLogger("odin.tools.registry")


class ToolRegistry:
    """Registry of all available tools.

    Tools are registered by name and can be looked up for execution
    or converted to LLM function declarations.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        name = tool.definition.name
        logger.info(f"Registering tool: {name}")
        self._tools[name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def all(self) -> List[BaseTool]:
        return list(self._tools.values())

    def names(self) -> List[str]:
        return list(self._tools.keys())

    def definitions(self) -> List[ToolDefinition]:
        return [t.definition for t in self._tools.values()]

    def to_gemini_tools(self) -> list[dict]:
        """Convert all tools to Gemini function declarations format."""
        declarations = []
        for tool in self._tools.values():
            defn = tool.definition
            declarations.append(
                {
                    "name": defn.name,
                    "description": defn.description,
                    "parameters": defn.parameters_schema,
                }
            )
        return declarations

    def __len__(self) -> int:
        return len(self._tools)
