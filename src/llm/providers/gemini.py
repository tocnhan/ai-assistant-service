from google import genai
from src.llm.base import LLMProvider, LLMResponse, LLMUsage

class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)

    async def generate(self, model, messages, tools=None,
                       temperature=0.7, max_tokens=2048, **kwargs) -> LLMResponse:
        response = await self.client.aio.models.generate_content(
            model=model,
            contents=self._convert_messages(messages),
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
            raw_response={}
        )

    def _convert_messages(self, messages: list[dict]) -> list:
        result = []
        for m in messages:
            if m["role"] == "system":
                continue  # Gemini xử lý system prompt khác, bỏ qua tạm
            result.append({"role": m["role"], "parts": [{"text": m["content"]}]})
        return result

    async def stream(self, model, messages, **kwargs):
        raise NotImplementedError

    def supports_streaming(self) -> bool:
        return False