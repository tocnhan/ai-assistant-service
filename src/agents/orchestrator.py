# src/agents/orchestrator.py
from src.agents.classifier import ClassifierAgent
from src.agents.registry import AgentRegistry
from src.memory.conversation import ConversationMemory



class Orchestrator:
    _classifier: ClassifierAgent | None = None  # class-level cache

    @classmethod
    def _get_classifier(cls) -> ClassifierAgent:
        from src.llm.registry import LLMRegistry
        available = LLMRegistry.list_providers()
        
        if cls._classifier is None or cls._classifier.provider not in available:
            cls._classifier = ClassifierAgent()
            print(f"[DEBUG] Classifier dùng: {cls._classifier.provider} / {cls._classifier.model}")
        
        return cls._classifier
    def __init__(self, company_guid: str, conversation_id: str | None = None):
        self.company_guid = company_guid
        self.conversation_id = conversation_id
        self.memory = ConversationMemory(company_guid)

    async def classify(self, user_message: str) -> dict:
        return await self._get_classifier().classify(user_message)

    async def run_stream(self, user_message: str, intent_hint: str | None = None):
        import time
        started = time.time()

        if intent_hint:
            intent = intent_hint
            confidence = 1.0
        else:
            result = await self.classify(user_message)
            intent = result["intent"]
            confidence = result.get("confidence", 0.5)

        yield {"type": "intent", "intent": intent, "confidence": confidence}

        history = []
        if self.conversation_id:
            history = await self.memory.get(self.conversation_id)

        from src.llm.selector import ModelSelector
        selector = await ModelSelector.from_db(self.company_guid)
        executor = AgentRegistry.get_executor(intent, selector=selector)
        messages = history + [{"role": "user", "content": user_message}]

        full_response = ""
        final_usage = None

        async for chunk in executor.stream(messages):
            if chunk.delta:
                full_response += chunk.delta
                yield {"type": "delta", "delta": chunk.delta}
            if chunk.usage:
                final_usage = chunk.usage

        if self.conversation_id:
            await self.memory.append(self.conversation_id, "user", user_message)
            await self.memory.append(self.conversation_id, "assistant", full_response)

        latency_ms = int((time.time() - started) * 1000)
        yield {
            "type": "done",
            "latency_ms": latency_ms,
            "usage": {
                "total_tokens": final_usage.total_tokens if final_usage else 0,
                "prompt_tokens": final_usage.prompt_tokens if final_usage else 0,
                "output_tokens": final_usage.output_tokens if final_usage else 0,
            },
        }

