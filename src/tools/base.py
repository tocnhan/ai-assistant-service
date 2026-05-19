# src/tools/base.py
from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    input_schema: dict = {}

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        ...

    def to_spec(self) -> dict:
        """JSON Schema spec để truyền vào LLM tool calling."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class ToolRegistry:
    _tools: dict[str, BaseTool] = {}

    @classmethod
    def register(cls, tool: BaseTool):
        cls._tools[tool.name] = tool

    @classmethod
    def get(cls, name: str) -> BaseTool:
        if name not in cls._tools:
            raise ValueError(f"Tool '{name}' chưa được register.")
        return cls._tools[name]

    @classmethod
    def list_tools(cls) -> list[str]:
        return list(cls._tools.keys())

    @classmethod
    def get_allowed(cls, whitelist: list[str]) -> list[BaseTool]:
        """Lấy các tool trong whitelist, bỏ qua tool không tồn tại."""
        return [cls._tools[name] for name in whitelist if name in cls._tools]