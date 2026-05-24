from src.llm.registry import LLMRegistry
from src.llm.base import LLMProvider

# Default config theo agent role
DEFAULT_MODELS = {
    "classifier": ("deepseek", "deepseek-chat"),
    "executor":   ("deepseek", "deepseek-chat"),
    "summarizer": ("deepseek", "deepseek-chat"),
    "premium":    ("anthropic", "claude-haiku-4-5"),
}

class ModelSelector:
    def __init__(self, tenant_overrides: dict = None):
        self._overrides = tenant_overrides or {}
    @classmethod
    async def from_db(cls, company_guid: str) -> "ModelSelector":
        try:
            from src.db.session import DatabasePool
            async with DatabasePool._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT agent_role, provider, model
                    FROM ai_service.tenant_model_overrides
                    WHERE company_guid = $1::uuid
                    """,
                    company_guid,
                )
            overrides = {
                row["agent_role"]: {
                    "provider": row["provider"],
                    "model":    row["model"],
                }
                for row in rows
            }
            return cls(tenant_overrides=overrides)
        except Exception:
            return cls()  # fallback về default, không crash request

    def select(self, role: str) -> tuple[str, str]:
        available = LLMRegistry.list_providers()

        if role in self._overrides:
            o = self._overrides[role]
            # ✅ check provider có available không trước khi return
            if o["provider"] in available:
                return o["provider"], o["model"]
            # provider không available → fallthrough xuống default

        if role in DEFAULT_MODELS:
            provider, model = DEFAULT_MODELS[role]
            if provider in available:
                return provider, model

        # Ultimate fallback
        if not available:
            raise RuntimeError("Không có LLM provider nào được register")
        provider = available[0]
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