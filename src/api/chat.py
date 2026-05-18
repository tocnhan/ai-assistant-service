from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from src.llm.registry import LLMRegistry

router = APIRouter(prefix="/chat", tags=["chat"])


class Message(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]
    model: str = "gemini-2.0-flash"
    provider: str = "gemini"
    temperature: float = 0.7
    max_tokens: int = 2048


class TokenUsage(BaseModel):
    prompt_tokens: int
    output_tokens: int
    cached_tokens: int
    thoughts_tokens: int
    total_tokens: int


class ChatResponse(BaseModel):
    text: str
    finish_reason: str
    usage: TokenUsage
    provider: str
    model: str


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        provider = LLMRegistry.get(req.provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    messages = [m.model_dump() for m in req.messages]

    try:
        result = await provider.generate(
            model=req.model,
            messages=messages,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    return ChatResponse(
        text=result.text,
        finish_reason=result.finish_reason,
        usage=TokenUsage(
            prompt_tokens=result.usage.prompt_tokens,
            output_tokens=result.usage.output_tokens,
            cached_tokens=result.usage.cached_tokens,
            thoughts_tokens=result.usage.thoughts_tokens,
            total_tokens=result.usage.total_tokens,
        ),
        provider=req.provider,
        model=req.model,
    )
