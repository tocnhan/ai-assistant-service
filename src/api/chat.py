# src/api/chat.py
import time
import json
import asyncio
from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel
from src.llm.registry import LLMRegistry
from src.llm.selector import ModelSelector
from src.agents.orchestrator import Orchestrator
from src.services.usage_logger import log_usage_background
from starlette.responses import StreamingResponse as StarletteStreamingResponse


router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    intent_hint: str | None = None


# ── Non-streaming (backward compat) ──────────────────────────────────────────
@router.post("/chat")
async def chat(request: Request, body: ChatRequest):
    company_guid = request.state.company_guid
    user_guid    = request.state.user_guid
    request_id   = request.state.request_id

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
        "provider": provider,
        "model": model,
        "usage": {
            "total_tokens": response.usage.total_tokens,
            "prompt_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    }


# ── Streaming SSE ─────────────────────────────────────────────────────────────
@router.post("/chat/stream")
async def chat_stream(request: Request, body: ChatRequest):
    company_guid = request.state.company_guid
    user_guid    = request.state.user_guid
    request_id   = request.state.request_id

    orchestrator = Orchestrator(
        company_guid=company_guid,
        conversation_id=body.conversation_id,
    )

    async def event_generator():
        started = time.time()
        final_usage = None

        try:
            if not body.intent_hint:
                intent_result = await orchestrator.classify(body.message)
                intent = intent_result["intent"]
            else:
                intent = body.intent_hint

            yield _sse({"type": "intent", "intent": intent})

            async for chunk in orchestrator.stream(
                user_message=body.message,
                intent_hint=intent,
            ):
                if chunk.delta:
                    yield _sse({"type": "delta", "delta": chunk.delta})
                if chunk.usage:
                    final_usage = chunk.usage

            latency_ms = int((time.time() - started) * 1000)
            yield _sse({
                "type": "done",
                "request_id": request_id,
                "latency_ms": latency_ms,
                "usage": {
                    "total_tokens": final_usage.total_tokens if final_usage else 0,
                    "prompt_tokens": final_usage.prompt_tokens if final_usage else 0,
                    "output_tokens": final_usage.output_tokens if final_usage else 0,
                } if final_usage else {},
            })

            if final_usage:
                selector = ModelSelector()
                provider, model = selector.select("executor")
                log_usage_background(
                    company_guid=company_guid,
                    user_guid=user_guid,
                    request_id=request_id,
                    agent_name="orchestrator",
                    provider=provider,
                    model=model,
                    usage=final_usage,
                    latency_ms=latency_ms,
                )

        except Exception as e:
            yield _sse({"type": "error", "message": str(e)})

    return StarletteStreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"