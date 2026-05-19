from openai import AsyncOpenAI
from src.llm.base import LLMProvider, LLMResponse, LLMUsage, LLMStreamChunk
from typing import AsyncIterator

class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, base_url: str = None):
        self.client = AsyncOpenAI(
            api_key=api_key,
            **({"base_url": base_url} if base_url else {})
        )

    async def generate(self, model, messages, tools=None,
                       temperature=0.7, max_tokens=2048, **kwargs) -> LLMResponse:
        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        u = response.usage
        d = getattr(u, "completion_tokens_details", None)
        p = getattr(u, "prompt_tokens_details", None)

        usage = LLMUsage(
            prompt_tokens=u.prompt_tokens,
            output_tokens=u.completion_tokens,
            # cached_tokens nằm trong prompt_tokens_details
            cached_tokens=getattr(p, "cached_tokens", 0) or 0,
            # thoughts_tokens = reasoning tokens (o-series models)
            thoughts_tokens=getattr(d, "reasoning_tokens", 0) or 0,
            total_tokens=u.total_tokens,
        )
        return LLMResponse(
            text=response.choices[0].message.content or "",
            usage=usage,
            finish_reason=response.choices[0].finish_reason,
            raw_response={}
        )

    async def stream(self, model, messages, **kwargs) -> AsyncIterator[LLMStreamChunk]:
        stream = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 2048),
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            delta = ""
            if chunk.choices:
                delta = chunk.choices[0].delta.content or ""

            is_final = (
                bool(chunk.choices) and chunk.choices[0].finish_reason is not None
            )

            usage = None
            if chunk.usage:
                u = chunk.usage
                usage = LLMUsage(
                    prompt_tokens=u.prompt_tokens,
                    output_tokens=u.completion_tokens,
                    total_tokens=u.total_tokens,
                )

            yield LLMStreamChunk(delta=delta, is_final=is_final, usage=usage)

    def supports_streaming(self) -> bool:
        return True