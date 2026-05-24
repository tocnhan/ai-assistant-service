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
    current_screen: str | None = None
    business_rules: str | None = None


# ── Non-streaming (backward compat) ──────────────────────────────────────────
@router.post("/chat")
async def chat(request: Request, body: ChatRequest):
    company_guid = request.state.company_guid
    user_guid    = request.state.user_guid
    request_id   = request.state.request_id

    started = time.time()
    orchestrator = Orchestrator(
        company_guid=company_guid,
        conversation_id=body.conversation_id,
    )

    # Collect full response từ stream
    full_response = ""
    final_event = {}
    async for event in orchestrator.run_stream(
        user_message=body.message,
        intent_hint=body.intent_hint,
        current_screen=body.current_screen,
        business_rules=body.business_rules,
    ):
        if event["type"] == "delta":
            full_response += event["delta"]
        if event["type"] == "done":
            final_event = event

    latency_ms = int((time.time() - started) * 1000)
    usage = final_event.get("usage", {})

    log_usage_background(
        company_guid=company_guid,
        user_guid=user_guid,
        request_id=request_id,
        agent_name="chat",
        provider=final_event.get("provider", "unknown"),
        model=final_event.get("model", "unknown"),
        usage=LLMUsage(
            prompt_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        ),
        latency_ms=latency_ms,
    )

    return {
        "response": full_response,
        "request_id": request_id,
        "provider": final_event.get("provider", "unknown"),
        "model": final_event.get("model", "unknown"),
        "usage": usage,
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
        final_usage = None
        started = time.time()
        try:
            async for event in orchestrator.run_stream(
                user_message=body.message,
                intent_hint=body.intent_hint,
                current_screen=body.current_screen,
                business_rules=body.business_rules,
            ):
                if isinstance(event, dict) and event.get("type") == "done":
                    from src.llm.base import LLMUsage
                    u = event.get("usage", {})
                    log_usage_background(
                        company_guid=company_guid,
                        user_guid=user_guid,
                        request_id=request_id,
                        agent_name="chat_stream",
                        provider=event.get("provider", "unknown"),
                        model=event.get("model", "unknown"),
                        usage=LLMUsage(
                            prompt_tokens=u.get("prompt_tokens", 0),
                            output_tokens=u.get("output_tokens", 0),
                            total_tokens=u.get("total_tokens", 0),
                        ),
                        latency_ms=event.get("latency_ms", 0),
                    )
                yield _sse(event)

        except Exception as e:
            import traceback
            traceback.print_exc()

            if final_usage is not None:
                from src.llm.base import LLMUsage
                log_usage_background(
                    company_guid=company_guid,
                    user_guid=user_guid,
                    request_id=request_id,
                    agent_name="chat_stream",
                    provider="unknown",
                    model="unknown",
                    usage=LLMUsage(
                        prompt_tokens=final_usage.prompt_tokens,
                        output_tokens=final_usage.output_tokens,
                        total_tokens=final_usage.total_tokens,
                    ),
                    latency_ms=int((time.time() - started) * 1000),
                    success=False,
                    error_code=type(e).__name__,
                )

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
    if isinstance(data, str):
        data = {"type": "raw", "text": data}
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"