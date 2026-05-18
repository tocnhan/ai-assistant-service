from src.llm.base import LLMProvider
from src.core.config import settings

class LLMRegistry:
    _providers: dict[str, LLMProvider] = {}

    @classmethod
    def register_all(cls):
        if settings.GEMINI_API_KEY:
            from src.llm.providers.gemini import GeminiProvider
            cls._providers["gemini"] = GeminiProvider(settings.GEMINI_API_KEY)
        if settings.OPENAI_API_KEY:
            from src.llm.providers.openai_provider import OpenAIProvider
            cls._providers["openai"] = OpenAIProvider(settings.OPENAI_API_KEY)

    @classmethod
    def get(cls, provider_name: str) -> LLMProvider:
        if provider_name not in cls._providers:
            raise ValueError(f"Provider '{provider_name}' not registered. Available: {list(cls._providers.keys())}")
        return cls._providers[provider_name]

    @classmethod
    def list_providers(cls) -> list[str]:
        return list(cls._providers.keys())