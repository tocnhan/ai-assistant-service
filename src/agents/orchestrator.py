# src/agents/orchestrator.py
import time
from src.agents.classifier import ClassifierAgent
from src.agents.registry import AgentRegistry
from src.memory.conversation import ConversationMemory
from src.packs.resolver import resolve_for_tenant
from src.packs.template_engine import render_prompt, build_context


class Orchestrator:
    _classifier: ClassifierAgent | None = None

    @classmethod
    def _get_classifier(cls) -> ClassifierAgent:
        from src.llm.registry import LLMRegistry
        available = LLMRegistry.list_providers()
        if cls._classifier is None or cls._classifier.provider not in available:
            cls._classifier = ClassifierAgent()
        return cls._classifier

    def __init__(self, company_guid: str, conversation_id: str | None = None):
        self.company_guid = company_guid
        self.conversation_id = conversation_id
        self.memory = ConversationMemory(company_guid)

    async def run_stream(
        self,
        user_message: str,
        intent_hint: str | None = None,
        current_screen: str | None = None,
        business_rules: str | None = None,
    ):
        started = time.time()

        # 1. Load effective config cho tenant
        effective = await resolve_for_tenant(self.company_guid)

        # 2. Classify intent
        if intent_hint and intent_hint in effective.intents:
            intent = intent_hint
            confidence = 1.0
        else:
            result = await self._get_classifier().classify(user_message)
            intent = result["intent"]
            confidence = result.get("confidence", 0.5)

            if intent not in effective.intents:
                intent = "general_chat"
                confidence = 0.3

        yield {"type": "intent", "intent": intent, "confidence": confidence}

        # 3. Render system prompt từ template
        template_key = f"{intent}:system"
        template_text = effective.prompts.get(
            template_key,
            "Bạn là AI assistant hữu ích.",
        )
        tenant_name = await _get_tenant_name(self.company_guid)
        context = build_context(
            tenant_name=tenant_name,
            current_screen=current_screen,
            business_rules=business_rules,
        )
        rendered_prompt = render_prompt(template_text, context)

        # 4. Load conversation history
        history = []
        if self.conversation_id:
            history = await self.memory.get(self.conversation_id)

        # 5. Lấy executor
        from src.llm.selector import ModelSelector
        tenant_overrides = {
            role: cfg for role, cfg in effective.default_models.items()
        }
        selector = ModelSelector(tenant_overrides=tenant_overrides)
        executor = AgentRegistry.get_executor(
            intent=intent,
            selector=selector,
            system_prompt_override=rendered_prompt,
        )

        messages = history + [{"role": "user", "content": user_message}]

        # 6. Stream response
        full_response = ""
        final_usage = None

        async for chunk in executor.stream(messages):
            if chunk.delta:
                full_response += chunk.delta
                yield {"type": "delta", "delta": chunk.delta}
            if chunk.usage:
                final_usage = chunk.usage

        # 7. Persist memory
        if self.conversation_id:
            await self.memory.append(self.conversation_id, "user", user_message)
            await self.memory.append(self.conversation_id, "assistant", full_response)

        latency_ms = int((time.time() - started) * 1000)
        yield {
            "type": "done",
            "latency_ms": latency_ms,
            "pack_id": effective.pack_id,
            "usage": {
                "total_tokens": final_usage.total_tokens if final_usage else 0,
                "prompt_tokens": final_usage.prompt_tokens if final_usage else 0,
                "output_tokens": final_usage.output_tokens if final_usage else 0,
            },
        }


async def _get_tenant_name(company_guid: str) -> str:
    try:
        from src.db.session import DatabasePool
        async with DatabasePool._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT display_name FROM ai_service.tenants WHERE company_guid = $1::uuid",
                company_guid,
            )
        return row["display_name"] if row and row["display_name"] else company_guid
    except Exception:
        return company_guid