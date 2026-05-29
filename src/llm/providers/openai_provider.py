from openai import AsyncOpenAI
from src.llm.base import LLMProvider, LLMResponse, LLMUsage, LLMStreamChunk
from src.core.config import settings
from typing import AsyncIterator
from langfuse.openai import AsyncOpenAI as LangfuseAsyncOpenAI


def _make_client(api_key: str, base_url: str = None) -> AsyncOpenAI:
    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url

    if settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY:
        import os
        os.environ["LANGFUSE_PUBLIC_KEY"] = settings.LANGFUSE_PUBLIC_KEY
        os.environ["LANGFUSE_SECRET_KEY"] = settings.LANGFUSE_SECRET_KEY
        os.environ["LANGFUSE_HOST"] = settings.LANGFUSE_HOST or "https://cloud.langfuse.com"
        return LangfuseAsyncOpenAI(**kwargs)
    return AsyncOpenAI(**kwargs)


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, base_url: str = None):
        self.client = _make_client(api_key, base_url)
        self._langfuse = None

    @property
    def langfuse(self):
        if self._langfuse is None:
            self._langfuse = _get_langfuse()
        return self._langfuse

    async def generate(self, model, messages, tools=None,
                       temperature=0.7, max_tokens=2048, **kwargs) -> LLMResponse:
        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            name="generate",  # Langfuse trace name
        )
        u = response.usage
        d = getattr(u, "completion_tokens_details", None)
        p = getattr(u, "prompt_tokens_details", None)

        usage = LLMUsage(
            prompt_tokens=u.prompt_tokens,
            output_tokens=u.completion_tokens,
            cached_tokens=getattr(p, "cached_tokens", 0) or 0,
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
            name="stream",  # Langfuse trace name
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
                d = getattr(u, "completion_tokens_details", None)
                p = getattr(u, "prompt_tokens_details", None)
                usage = LLMUsage(
                    prompt_tokens=u.prompt_tokens,
                    output_tokens=u.completion_tokens,
                    cached_tokens=getattr(p, "cached_tokens", 0) or 0,
                    thoughts_tokens=getattr(d, "reasoning_tokens", 0) or 0,
                    total_tokens=u.total_tokens,
                )

            yield LLMStreamChunk(delta=delta, is_final=is_final, usage=usage)

    def supports_streaming(self) -> bool:
        return True