from google import genai
from google.genai import types
from src.llm.base import LLMProvider, LLMResponse, LLMUsage, LLMStreamChunk
from typing import AsyncIterator, Optional

class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)

    async def generate(
        self,
        model: str,
        messages: list[dict],
        tools=None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        thinking_budget: Optional[int] = None,
        **kwargs,
    ) -> LLMResponse:
        # Tách system prompt ra — Gemini dùng system_instruction riêng
        system_parts = [
            m["content"] for m in messages if m["role"] == "system"
        ]
        non_system = [m for m in messages if m["role"] != "system"]

        config_kwargs: dict = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if thinking_budget is not None:
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_budget=thinking_budget
            )
        if system_parts:
            config_kwargs["system_instruction"] = "\n\n".join(system_parts)

        response = await self.client.aio.models.generate_content(
            model=model,
            contents=self._convert_messages(non_system),
            config=types.GenerateContentConfig(**config_kwargs),
        )

        um = response.usage_metadata
        usage = LLMUsage(
            prompt_tokens=um.prompt_token_count or 0,
            output_tokens=um.candidates_token_count or 0,
            cached_tokens=um.cached_content_token_count or 0,
            thoughts_tokens=um.thoughts_token_count or 0,
            total_tokens=um.total_token_count or 0,
        )
        return LLMResponse(
            text=response.text,
            usage=usage,
            finish_reason=str(response.candidates[0].finish_reason),
            raw_response={},
        )

    def _convert_messages(self, messages: list[dict]) -> list:
        result = []
        for m in messages:
            role = "model" if m["role"] == "assistant" else m["role"]
            result.append({"role": role, "parts": [{"text": m["content"]}]})
        return result

    async def stream(self, model, messages, **kwargs) -> AsyncIterator[LLMStreamChunk]:
        raise NotImplementedError("Streaming implement ở Sprint 4")

    def supports_streaming(self) -> bool:
        return False