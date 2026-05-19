from src.llm.registry import LLMRegistry
from src.llm.base import LLMProvider

# Default config theo agent role
DEFAULT_MODELS = {
    "classifier": ("groq", "llama-3.1-8b-instant"),    # nhanh, rẻ
    "executor":   ("gemini", "gemini-2.5-flash"),       # balance
    "summarizer": ("deepseek", "deepseek-chat"),        # rẻ
    "premium":    ("anthropic", "claude-sonnet-4-6"),   # quality cao
}

class ModelSelector:
    def __init__(self, tenant_overrides: dict = None):
        self._overrides = tenant_overrides or {}

    def select(self, role: str) -> tuple[str, str]:
        """Trả về (provider_name, model_name) cho role."""
        if role in self._overrides:
            o = self._overrides[role]
            return o["provider"], o["model"]

        if role in DEFAULT_MODELS:
            provider, model = DEFAULT_MODELS[role]
            # Fallback nếu provider chưa được register (key chưa set)
            if provider in LLMRegistry.list_providers():
                return provider, model

        # Ultimate fallback: provider đầu tiên available
        available = LLMRegistry.list_providers()
        if not available:
            raise RuntimeError("Không có LLM provider nào được register")
        provider = available[0]
        # Model mặc định của provider đó
        fallback_models = {
            "gemini": "gemini-2.5-flash-lite",
            "openai": "gpt-4o-mini",
            "anthropic": "claude-haiku-4-5",
            "deepseek": "deepseek-chat",
            "groq": "llama-3.1-8b-instant",
        }
        return provider, fallback_models.get(provider, "unknown")

    def get_provider(self, role: str) -> tuple[LLMProvider, str]:
        """Convenience: trả về (provider_instance, model_name)."""
        provider_name, model = self.select(role)
        return LLMRegistry.get(provider_name), model