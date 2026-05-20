# src/agents/registry.py
from src.agents.base import BaseAgent
from src.llm.selector import DEFAULT_MODELS


def _make_executor(provider: str, model: str, system_prompt: str = "") -> BaseAgent:
    from src.agents.base import BaseAgent

    class ExecutorAgent(BaseAgent):
        pass

    return ExecutorAgent(
        provider=provider,
        model=model,
        system_prompt=system_prompt,
        temperature=0.7,
        max_tokens=2048,
    )


# Map intent → (provider, model, system_prompt)
_INTENT_CONFIG: dict[str, tuple] = {
    "general_chat": (
        DEFAULT_MODELS["executor"][0],
        DEFAULT_MODELS["executor"][1],
        "Bạn là AI assistant hữu ích, trả lời ngắn gọn và chính xác.",
    ),
    "search_knowledge": (
        DEFAULT_MODELS["executor"][0],
        DEFAULT_MODELS["executor"][1],
        "Bạn là AI assistant chuyên tìm kiếm và tổng hợp thông tin.",
    ),
    "api_action": (
        DEFAULT_MODELS["executor"][0],
        DEFAULT_MODELS["executor"][1],
        "Bạn là AI assistant thực hiện các thao tác qua API. Xác nhận rõ ràng trước khi thực hiện.",
    ),
    "summarize": (
        DEFAULT_MODELS["summarizer"][0],
        DEFAULT_MODELS["summarizer"][1],
        "Bạn là AI assistant chuyên tóm tắt nội dung súc tích, đầy đủ ý.",
    ),
    "unknown": (
        DEFAULT_MODELS["executor"][0],
        DEFAULT_MODELS["executor"][1],
        "Bạn là AI assistant hữu ích.",
    ),
}


class AgentRegistry:
    @staticmethod
    def get_executor(intent: str, selector=None) -> BaseAgent:
        config = _INTENT_CONFIG.get(intent, _INTENT_CONFIG["unknown"])
        _, _, system_prompt = config  # chỉ lấy system_prompt từ config mặc định

        if selector:
            provider, model = selector.select("executor")
        else:
            provider, model = config[0], config[1]

        return _make_executor(provider, model, system_prompt)