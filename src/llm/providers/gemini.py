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

    @property
    def langfuse(self):
        if 'langfuse' not in self.__dict__:
            self.__dict__['langfuse'] = _get_langfuse()
        return self.__dict__['langfuse']

    async def generate(self, model, messages, tools=None,
                       temperature=0.7, max_tokens=2048,
                       thinking_budget=None, **kwargs) -> LLMResponse:
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        non_system = [m for m in messages if m["role"] != "system"]

        config_kwargs = {"temperature": temperature, "max_output_tokens": max_tokens}
        if thinking_budget is not None:
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=thinking_budget)
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

        if self.langfuse:
            self.langfuse.start_observation(
                name="gemini.generate",
                model=model,
                as_type="generation",
                input=messages,
                output=response.text,
                usage_details={"input": usage.prompt_tokens, "output": usage.output_tokens, "total": usage.total_tokens},
            )

        return LLMResponse(text=response.text, usage=usage,
                           finish_reason=str(response.candidates[0].finish_reason), raw_response={})

    def _convert_messages(self, messages):
        result = []
        for m in messages:
            role = "model" if m["role"] == "assistant" else m["role"]
            result.append({"role": role, "parts": [{"text": m["content"]}]})
        return result

    async def stream(self, model, messages, **kwargs) -> AsyncIterator[LLMStreamChunk]:
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        non_system = [m for m in messages if m["role"] != "system"]

        config_kwargs = {
            "temperature": kwargs.get("temperature", 0.7),
            "max_output_tokens": kwargs.get("max_tokens", 2048),
        }
        if system_parts:
            config_kwargs["system_instruction"] = "\n\n".join(system_parts)

        start = time.time()
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
                if self.langfuse:
                    self.langfuse.start_observation(
                        name="gemini.stream",
                        model=model,
                        input=messages,
                        as_type="generation",
                        output="[streamed]",
                        usage_details={"input": usage.prompt_tokens, "output": usage.output_tokens, "total": usage.total_tokens},
                    )

            yield LLMStreamChunk(delta=chunk.text or "", is_final=is_final, usage=usage)

    def supports_streaming(self) -> bool:
        return True