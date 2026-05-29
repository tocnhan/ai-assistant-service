from google import genai
from google.genai import types
from src.llm.base import LLMProvider, LLMResponse, LLMUsage, LLMStreamChunk
from src.core.config import settings
from typing import AsyncIterator, Optional
import time

def _get_langfuse():
    if settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY:
        from langfuse import Langfuse
        return Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST or "https://cloud.langfuse.com",
        )
    return None


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self.langfuse = None
        
    @property
    def langfuse(self):
        if self._langfuse is None:
            self._langfuse = _get_langfuse()
        return self._langfuse

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
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
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

        start = time.time()
        response = await self.client.aio.models.generate_content(
            model=model,
            contents=self._convert_messages(non_system),
            config=types.GenerateContentConfig(**config_kwargs),
        )
        latency = int((time.time() - start) * 1000)

        um = response.usage_metadata
        usage = LLMUsage(
            prompt_tokens=um.prompt_token_count or 0,
            output_tokens=um.candidates_token_count or 0,
            cached_tokens=um.cached_content_token_count or 0,
            thoughts_tokens=um.thoughts_token_count or 0,
            total_tokens=um.total_token_count or 0,
        )

        # Langfuse trace
        if self.langfuse:
            trace = self.langfuse.trace(name="gemini.generate")
            trace.generation(
                name="generate",
                model=model,
                input=messages,
                output=response.text,
                usage={
                    "input": usage.prompt_tokens,
                    "output": usage.output_tokens,
                    "total": usage.total_tokens,
                },
                latency=latency,
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
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        non_system = [m for m in messages if m["role"] != "system"]

        config_kwargs: dict = {
            "temperature": kwargs.get("temperature", 0.7),
            "max_output_tokens": kwargs.get("max_tokens", 2048),
        }
        if system_parts:
            config_kwargs["system_instruction"] = "\n\n".join(system_parts)

        start = time.time()
        trace = self.langfuse.trace(name="gemini.stream") if self.langfuse else None

        async for chunk in await self.client.aio.models.generate_content_stream(
            model=model,
            contents=self._convert_messages(non_system),
            config=types.GenerateContentConfig(**config_kwargs),
        ):
            is_final = chunk.candidates[0].finish_reason is not None
            usage = None
            if is_final and chunk.usage_metadata:
                um = chunk.usage_metadata
                usage = LLMUsage(
                    prompt_tokens=um.prompt_token_count or 0,
                    output_tokens=um.candidates_token_count or 0,
                    cached_tokens=um.cached_content_token_count or 0,
                    thoughts_tokens=um.thoughts_token_count or 0,
                    total_tokens=um.total_token_count or 0,
                )
                if trace:
                    trace.generation(
                        name="stream",
                        model=model,
                        input=messages,
                        output="[streamed]",
                        usage={
                            "input": usage.prompt_tokens,
                            "output": usage.output_tokens,
                            "total": usage.total_tokens,
                        },
                        latency=int((time.time() - start) * 1000),
                    )

            yield LLMStreamChunk(
                delta=chunk.text or "",
                is_final=is_final,
                usage=usage,
            )

    def supports_streaming(self) -> bool:
        return True