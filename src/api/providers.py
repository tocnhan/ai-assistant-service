from fastapi import APIRouter
from pydantic import BaseModel
from src.llm.registry import LLMRegistry

router = APIRouter(prefix="/providers", tags=["providers"])

# Default models per provider
_PROVIDER_MODELS: dict[str, list[str]] = {
    "gemini": [
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-3.5-turbo",
    ],
    "gemini": [
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
    ],
    "deepseek": [
        "deepseek-v3-exp",
        "deepseek-chat-v3.1",
    ],
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
    ],
    "anthropic": [
        "claude-sonnet-4-5",
        "claude-haiku-4-5",
        "claude-opus-4-5",
    ],
    "moonshot": [
        "kimi-k2",
        "kimi-k2-thinking",
    ],
}


class ProviderInfo(BaseModel):
    name: str
    available: bool
    models: list[str]
    supports_streaming: bool
    supports_tools: bool


class ProvidersResponse(BaseModel):
    providers: list[ProviderInfo]


@router.get("", response_model=ProvidersResponse)
async def list_providers():
    registered = LLMRegistry.list_providers()
    result = []
    for name, models in _PROVIDER_MODELS.items():
        if name in registered:
            p = LLMRegistry.get(name)
            result.append(ProviderInfo(
                name=name,
                available=True,
                models=models,
                supports_streaming=p.supports_streaming(),
                supports_tools=p.supports_tools(),
            ))
        else:
            result.append(ProviderInfo(
                name=name,
                available=False,
                models=models,
                supports_streaming=False,
                supports_tools=False,
            ))
    return ProvidersResponse(providers=result)
