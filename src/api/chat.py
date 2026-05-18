# src/api/chat.py
import time
from fastapi import APIRouter, Request
from pydantic import BaseModel
from src.llm.registry import LLMRegistry
from src.core.config import settings
from src.services.usage_logger import log_usage_background

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    intent_hint: str | None = None

@router.post("/chat")
async def chat(request: Request, body: ChatRequest):
    company_guid = request.state.company_guid
    user_guid    = request.state.user_guid
    request_id   = request.state.request_id

    provider_name = "gemini" if settings.GEMINI_API_KEY else "openai"
    model = "gemini-2.5-flash-lite" if provider_name == "gemini" else "gpt-4o-mini"

    provider = LLMRegistry.get(provider_name)

    started = time.time()
    response = await provider.generate(
        model=model,
        messages=[{"role": "user", "content": body.message}]
    )
    latency_ms = int((time.time() - started) * 1000)

    # Async log — không block response
    log_usage_background(
        company_guid=company_guid,
        user_guid=user_guid,
        request_id=request_id,
        agent_name="chat",
        provider=provider_name,
        model=model,
        usage=response.usage,
        latency_ms=latency_ms,
    )

    return {
        "response": response.text,
        "request_id": request_id,
        "company_guid": company_guid,
        "usage": {
            "total_tokens": response.usage.total_tokens,
            "prompt_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.output_tokens,
            "estimated_cost_usd": 0.0  # sẽ có sau khi seed pricing
        }
    }