# src/tools/base.py
import time
from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    input_schema: dict = {}

    @abstractmethod
    async def _run(self, **kwargs) -> Any:
        """Logic thật của tool viết ở đây."""
        ...

    async def execute(
        self,
        company_guid: str = "",
        conversation_id: str | None = None,
        request_id: str | None = None,
        agent_name: str = "",
        **kwargs,
    ) -> Any:
        from src.services.tool_logger import log_tool_call_background

        started = time.time()
        success = True
        error_message = None
        result = {}

        try:
            result = await self._run(**kwargs)
            return result
        except Exception as e:
            success = False
            error_message = str(e)
            result = {"error": error_message}
            raise
        finally:
            latency_ms = int((time.time() - started) * 1000)
            if company_guid:
                log_tool_call_background(
                    company_guid=company_guid,
                    conversation_id=conversation_id,
                    request_id=request_id,
                    agent_name=agent_name,
                    tool_name=self.name,
                    input_data=kwargs,
                    output_data=result if isinstance(result, dict) else {"result": str(result)},
                    latency_ms=latency_ms,
                    success=success,
                    error_message=error_message,
                )

    def to_spec(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def configure(self, config: dict) -> "BaseTool":
        """
        Nhận config từ DB (tenant_tool_configs.config),
        trả về instance mới đã được cấu hình.
        Override ở subclass nào cần config runtime.
        """
        return self

    def to_mcp_spec(self) -> dict:
        """MCP-compatible tool spec để export cho LLM."""
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
        return [cls._tools[name] for name in whitelist if name in cls._tools]
        
    @classmethod
    def get_configured(cls, name: str, config: dict) -> "BaseTool":
        """
        Lấy tool theo tên, inject config per-tenant vào.
        Trả về instance mới — không mutate instance gốc.
        """
        tool = cls.get(name)
        return tool.configure(config)