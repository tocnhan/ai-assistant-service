from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    thoughts_tokens: int = 0
    tool_tokens: int = 0
    total_tokens: int = 0

@dataclass
class LLMResponse:
    text: str
    usage: LLMUsage
    finish_reason: str
    raw_response: dict = field(default_factory=dict)

@dataclass
class LLMStreamChunk:
    delta: str
    is_final: bool = False
    usage: Optional[LLMUsage] = None

class LLMProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        model: str,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> LLMResponse:
        ...

    @abstractmethod
    async def stream(
        self,
        model: str,
        messages: list[dict],
        **kwargs
    ) -> AsyncIterator[LLMStreamChunk]:
        ...

    def supports_tools(self) -> bool:
        return True

    def supports_streaming(self) -> bool:
        return True