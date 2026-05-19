import anthropic
from src.llm.base import LLMProvider, LLMResponse, LLMUsage, LLMStreamChunk
from typing import AsyncIterator

class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)

    async def generate(self, model, messages, tools=None,
                       temperature=0.7, max_tokens=2048, **kwargs) -> LLMResponse:
        # Tách system message (Anthropic dùng param riêng)
        system = ""
        filtered = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                filtered.append(m)

        response = await self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system or anthropic.NOT_GIVEN,
            messages=filtered,
        )
        u = response.usage
        usage = LLMUsage(
            prompt_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            cached_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
            thoughts_tokens=0,  # Extended thinking tính riêng, Sprint 7
            total_tokens=u.input_tokens + u.output_tokens,
        )
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        return LLMResponse(
            text=text,
            usage=usage,
            finish_reason=response.stop_reason or "stop",
            raw_response={}
        )

    async def stream(self, model, messages, **kwargs) -> AsyncIterator[LLMStreamChunk]:
        system = ""
        filtered = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                filtered.append(m)

        async with self.client.messages.stream(
            model=model,
            max_tokens=kwargs.get("max_tokens", 2048),
            temperature=kwargs.get("temperature", 0.7),
            system=system or anthropic.NOT_GIVEN,
            messages=filtered,
        ) as stream:
            async for delta in stream.text_stream:
                yield LLMStreamChunk(delta=delta, is_final=False)

            # Chunk cuối kèm usage
            final = await stream.get_final_message()
            u = final.usage
            yield LLMStreamChunk(
                delta="",
                is_final=True,
                usage=LLMUsage(
                    prompt_tokens=u.input_tokens,
                    output_tokens=u.output_tokens,
                    cached_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
                    total_tokens=u.input_tokens + u.output_tokens,
                ),
            )

    def supports_streaming(self) -> bool:
        return True