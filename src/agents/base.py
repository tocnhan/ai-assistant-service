# src/agents/base.py
from abc import ABC, abstractmethod
from typing import AsyncIterator
from src.llm.base import LLMResponse, LLMStreamChunk
from src.llm.registry import LLMRegistry


class BaseAgent(ABC):
    def __init__(
        self,
        provider: str,
        model: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        tools: list = None,
    ):
        self.provider = provider
        self.model = model
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.tools = tools or []

    def _build_messages(self, messages: list[dict]) -> list[dict]:
        """Prepend system prompt nếu có."""
        if not self.system_prompt:
            return messages
        return [{"role": "system", "content": self.system_prompt}] + messages

    async def run(self, messages: list[dict]) -> LLMResponse:
        llm = LLMRegistry.get(self.provider)
        return await llm.generate(
            model=self.model,
            messages=self._build_messages(messages),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

    async def stream(self, messages: list[dict]) -> AsyncIterator[LLMStreamChunk]:
        llm = LLMRegistry.get(self.provider)
        async for chunk in llm.stream(
            model=self.model,
            messages=self._build_messages(messages),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        ):
            yield chunk