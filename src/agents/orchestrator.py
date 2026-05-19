# src/agents/orchestrator.py
from typing import AsyncIterator
from src.agents.classifier import ClassifierAgent
from src.agents.registry import AgentRegistry
from src.llm.base import LLMStreamChunk
from src.memory.conversation import ConversationMemory

classifier = ClassifierAgent()


class Orchestrator:
    def __init__(self, company_guid: str, conversation_id: str | None = None):
        self.company_guid = company_guid
        self.conversation_id = conversation_id
        self.memory = ConversationMemory(company_guid)

    async def classify(self, user_message: str) -> dict:
        return await classifier.classify(user_message)

    async def stream(
        self, user_message: str, intent_hint: str | None = None
    ) -> AsyncIterator[LLMStreamChunk]:
        # 1. Load history từ Redis
        history = []
        if self.conversation_id:
            history = await self.memory.get(self.conversation_id)

        # 2. Classify intent (hoặc dùng hint nếu FE truyền lên)
        if intent_hint:
            intent = intent_hint
        else:
            result = await self.classify(user_message)
            intent = result["intent"]

        # 3. Lấy executor phù hợp
        executor = AgentRegistry.get_executor(intent)

        # 4. Build messages với history
        messages = history + [{"role": "user", "content": user_message}]

        # 5. Stream response
        full_response = ""
        final_usage = None

        async for chunk in executor.stream(messages):
            full_response += chunk.delta
            if chunk.usage:
                final_usage = chunk.usage
            yield chunk

        # 6. Lưu turn mới vào memory
        if self.conversation_id:
            await self.memory.append(
                self.conversation_id, "user", user_message
            )
            await self.memory.append(
                self.conversation_id, "assistant", full_response
            )