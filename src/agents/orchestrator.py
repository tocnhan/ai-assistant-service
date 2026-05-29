# src/agents/orchestrator.py
import time
import asyncio
from src.agents.classifier import ClassifierAgent
from src.agents.registry import AgentRegistry
from src.llm.registry import LLMRegistry
from src.memory.conversation import ConversationMemory
from src.packs.resolver import resolve_for_tenant
from src.packs.template_engine import render_prompt, build_context
from src.services.tool_config import ToolConfigService


class Orchestrator:
    _classifier: ClassifierAgent | None = None
    _classifier_lock = asyncio.Lock()

    async def _load_tools(self, effective) -> list:
        """Load tools đã configured cho tenant này."""
        return await ToolConfigService.get_tools_for_tenant(
            company_guid=self.company_guid,
            whitelist=effective.tool_whitelist,
        )

    @classmethod
    async def _get_classifier(cls) -> ClassifierAgent:
        available = LLMRegistry.list_providers()
        if cls._classifier is not None and cls._classifier.provider in available:
            return cls._classifier

        async with cls._classifier_lock:
            if cls._classifier is None or cls._classifier.provider not in available:
                cls._classifier = ClassifierAgent()
        return cls._classifier

    def __init__(self, company_guid: str, conversation_id: str | None = None):
        self.company_guid = company_guid
        self.conversation_id = conversation_id
        self.memory = ConversationMemory(company_guid)

    # ── Helpers (non-generator) ───────────────────────────────────────────────

    async def _resolve_intent(
        self,
        user_message: str,
        intent_hint: str | None,
        effective_intents: list,
    ) -> tuple[str, float]:
        if intent_hint and intent_hint in effective_intents:
            return intent_hint, 1.0

        classifier = await self._get_classifier()
        result = await classifier.classify(user_message)
        intent = result["intent"]
        confidence = result.get("confidence", 0.5)

        if intent not in effective_intents:
            return "general_chat", 0.3

        return intent, confidence

    async def _render_system_prompt(
        self,
        intent: str,
        effective,
        current_screen: str | None,
        business_rules: str | None,
    ) -> str:
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
        return render_prompt(template_text, context)

    async def _build_executor(self, intent: str, effective, rendered_prompt: str, tools: list = None):
        from src.llm.selector import ModelSelector
        selector = await ModelSelector.from_db(self.company_guid)

        for role, cfg in effective.default_models.items():
            if role not in selector._overrides:
                selector._overrides[role] = cfg

        return AgentRegistry.get_executor(
            intent=intent,
            selector=selector,
            system_prompt_override=rendered_prompt,
        )

    # ── Main ──────────────────────────────────────────────────────────────────

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
        intent, confidence = await self._resolve_intent(
            user_message, intent_hint, effective.intents
        )
        yield {"type": "intent", "intent": intent, "confidence": confidence}

        # 3. Render system prompt
        rendered_prompt = await self._render_system_prompt(
            intent, effective, current_screen, business_rules
        )

        # 4. Load conversation history
        history = []
        if self.conversation_id:
            history = await self.memory.get(self.conversation_id)

        # 5. Build executor
        tools = await self._load_tools(effective)
        executor = await self._build_executor(intent, effective, rendered_prompt, tools)
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
            await self.memory.append_turn(
                self.conversation_id,
                user_content=user_message,
                assistant_content=full_response,
            )

        latency_ms = int((time.time() - started) * 1000)
        yield {
            "type": "done",
            "latency_ms": latency_ms,
            "pack_id": effective.pack_id,
            "provider": executor.provider,
            "model": executor.model,
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