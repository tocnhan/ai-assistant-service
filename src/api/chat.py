# src/api/chat.py
import time
from fastapi import APIRouter, Request
from pydantic import BaseModel
from src.llm.registry import LLMRegistry
from src.llm.selector import ModelSelector
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

    # Lấy tenant_model_overrides nếu có (Sprint 7 sẽ load từ DB)
    # Hiện tại để trống → dùng DEFAULT_MODELS
    selector = ModelSelector()
    provider, model = selector.select("executor")

    llm = LLMRegistry.get(provider)

    started = time.time()
    response = await llm.generate(
        model=model,
        messages=[{"role": "user", "content": body.message}]
    )
    latency_ms = int((time.time() - started) * 1000)

    log_usage_background(
        company_guid=company_guid,
        user_guid=user_guid,
        request_id=request_id,
        agent_name="chat",
        provider=provider,
        model=model,
        usage=response.usage,
        latency_ms=latency_ms,
    )

    return {
        "response": response.text,
        "request_id": request_id,
        "company_guid": company_guid,
        "provider": provider,
        "model": model,
        "usage": {
            "total_tokens": response.usage.total_tokens,
            "prompt_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.output_tokens,
        }
    }