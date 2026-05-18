from openai import AsyncOpenAI
from src.llm.base import LLMProvider, LLMResponse, LLMUsage

class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str):
        self.client = AsyncOpenAI(api_key=api_key)

    async def generate(self, model, messages, tools=None,
                       temperature=0.7, max_tokens=2048, **kwargs) -> LLMResponse:
        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        u = response.usage
        usage = LLMUsage(
            prompt_tokens=u.prompt_tokens,
            output_tokens=u.completion_tokens,
            total_tokens=u.total_tokens,
        )
        return LLMResponse(
            text=response.choices[0].message.content,
            usage=usage,
            finish_reason=response.choices[0].finish_reason,
            raw_response={}
        )

    async def stream(self, model, messages, **kwargs):
        raise NotImplementedError