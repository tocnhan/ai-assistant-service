# src/agents/registry.py
from src.agents.base import BaseAgent


def _make_executor(provider: str, model: str, system_prompt: str = "") -> BaseAgent:
    class ExecutorAgent(BaseAgent):
        pass

    return ExecutorAgent(
        provider=provider,
        model=model,
        system_prompt=system_prompt,
        temperature=0.7,
        max_tokens=2048,
    )


_DEFAULT_PROMPTS = {
    "general_chat": "Bạn là AI assistant hữu ích, trả lời ngắn gọn và chính xác.",
    "search_knowledge": "Bạn là AI assistant chuyên tìm kiếm và tổng hợp thông tin.",
    "api_action": "Bạn là AI assistant thực hiện các thao tác qua API. Xác nhận rõ ràng trước khi thực hiện.",
    "summarize": "Bạn là AI assistant chuyên tóm tắt nội dung súc tích, đầy đủ ý.",
    "unknown": "Bạn là AI assistant hữu ích.",
}


class AgentRegistry:
    @staticmethod
    def get_executor(
        intent: str,
        selector=None,
        system_prompt_override: str | None = None,
    ) -> BaseAgent:
        # Ưu tiên: prompt từ template engine > default hardcode
        system_prompt = system_prompt_override or _DEFAULT_PROMPTS.get(
            intent, _DEFAULT_PROMPTS["unknown"]
        )

        if selector:
            provider, model = selector.select("executor")
        else:
            from src.llm.selector import DEFAULT_MODELS
            provider, model = DEFAULT_MODELS["executor"]

        return _make_executor(provider, model, system_prompt)