# src/agents/classifier.py
import json
from src.llm.registry import LLMRegistry
from src.agents.base import BaseAgent

CLASSIFIER_PROMPT = """Bạn là intent classifier. Nhiệm vụ duy nhất: phân loại intent của user message.

Trả về JSON theo đúng format này, không thêm gì khác:
{"intent": "<intent_name>", "confidence": <0.0-1.0>}

Các intent hợp lệ:
- general_chat      : hỏi đáp thông thường, không thuộc nhóm nào dưới
- search_knowledge  : tìm kiếm thông tin trong knowledge base
- api_action        : thực hiện thao tác qua API (booking, tạo đơn, cập nhật...)
- summarize         : tóm tắt nội dung
- unknown           : không xác định được

Chỉ trả về JSON. Không giải thích."""


_CLASSIFIER_PRIORITY = [
    ("groq",      "llama-3.1-8b-instant"),
    ("deepseek",  "deepseek-chat"),
    ("gemini",    "gemini-2.5-flash-lite"),
    ("openai",    "gpt-4o-mini"),
    ("anthropic", "claude-haiku-4-5"),
]


def _pick_classifier_provider() -> tuple[str, str]:
    available = set(LLMRegistry.list_providers())
    for provider, model in _CLASSIFIER_PRIORITY:
        if provider in available:
            return provider, model
    raise RuntimeError(
        "Cần ít nhất 1 API key để chạy classifier"
    )


class ClassifierAgent(BaseAgent):
    def __init__(self):
        provider, model = _pick_classifier_provider()
        super().__init__(
            provider=provider,
            model=model,
            system_prompt=CLASSIFIER_PROMPT,
            temperature=0.1,
            max_tokens=64,
        )

    async def classify(self, user_message: str) -> dict:
        """Trả về {"intent": str, "confidence": float}"""
        response = await self.run([{"role": "user", "content": user_message}])

        try:
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result = json.loads(text.strip())
            # Validate
            if "intent" not in result:
                raise ValueError("missing intent")
            result["confidence"] = float(result.get("confidence", 0.5))
            return result
        except Exception:
            # Fallback nếu LLM không trả đúng JSON
            return {"intent": "general_chat", "confidence": 0.5}