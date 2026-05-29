import anthropic
import time
from src.llm.base import LLMProvider, LLMResponse, LLMUsage, LLMStreamChunk
from src.core.config import settings
from typing import AsyncIterator


def _get_langfuse():
    if settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY:
        from langfuse import Langfuse
        return Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST or "https://cloud.langfuse.com",
        )
    return None


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)

    @property
    def langfuse(self):
        if 'langfuse' not in self.__dict__:
            self.__dict__['langfuse'] = _get_langfuse()
        return self.__dict__['langfuse']

    async def generate(self, model, messages, tools=None,
                       temperature=0.7, max_tokens=2048, **kwargs) -> LLMResponse:
        system = ""
        filtered = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                filtered.append(m)

        start = time.time()
        response = await self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system or anthropic.NOT_GIVEN,
            messages=filtered,
        )
        latency = int((time.time() - start) * 1000)

        u = response.usage
        usage = LLMUsage(
            prompt_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            cached_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
            thoughts_tokens=0,
            total_tokens=u.input_tokens + u.output_tokens,
        )
        text = "".join(b.text for b in response.content if hasattr(b, "text"))

        if self.langfuse:
            self.langfuse.start_observation(
                name="anthropic.generate",
                model=model,
                as_type="generation",
                input=messages,
                output=text,
                usage_details={"input": usage.prompt_tokens, "output": usage.output_tokens, "total": usage.total_tokens},
            )

        return LLMResponse(text=text, usage=usage,
                           finish_reason=response.stop_reason or "stop", raw_response={})

    async def stream(self, model, messages, **kwargs) -> AsyncIterator[LLMStreamChunk]:
        system = ""
        filtered = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                filtered.append(m)

        start = time.time()
        async with self.client.messages.stream(
            model=model,
            max_tokens=kwargs.get("max_tokens", 2048),
            temperature=kwargs.get("temperature", 0.7),
            system=system or anthropic.NOT_GIVEN,
            messages=filtered,
        ) as stream:
            async for delta in stream.text_stream:
                yield LLMStreamChunk(delta=delta, is_final=False)

            final = await stream.get_final_message()
            u = final.usage
            usage = LLMUsage(
                prompt_tokens=u.input_tokens,
                output_tokens=u.output_tokens,
                cached_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
                total_tokens=u.input_tokens + u.output_tokens,
            )

            if self.langfuse:
                self.langfuse.start_observation(
                    name="anthropic.stream",
                    model=model,
                    as_type="generation",
                    input=messages,
                    output="[streamed]",
                    usage_details={"input": usage.prompt_tokens, "output": usage.output_tokens, "total": usage.total_tokens},
                )

            yield LLMStreamChunk(delta="", is_final=True, usage=usage)

    def supports_streaming(self) -> bool:
        return True