# scripts/seed_packs.py
import asyncio
import json
import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
import re
PACKS = [
    {
        "pack_id": "tourism@1.0.0",
        "display_name": "Du lịch & Khách sạn",
        "config": {
            "intents": ["general_chat", "search_knowledge", "api_action", "summarize", "unknown"],
            "tool_whitelist": ["qdrant_search", "http_api_call"],
            "default_models": {
                "classifier": {"provider": "groq", "model": "llama-3.1-8b-instant"},
                "executor": {"provider": "deepseek", "model": "deepseek-chat"},
            },
        },
    },
    {
        "pack_id": "generic@1.0.0",
        "display_name": "Gói chung (mọi ngành)",
        "config": {
            "intents": ["general_chat", "search_knowledge", "unknown"],
            "tool_whitelist": [],
            "default_models": {
                "classifier": {"provider": "groq", "model": "llama-3.1-8b-instant"},
                "executor": {"provider": "deepseek", "model": "deepseek-chat"},
            },
        },
    },
    {
        "pack_id": "spa_booking@1.0.0",
        "display_name": "Spa & Clinic Booking",
        "config": {
            "intents": ["general_chat", "api_action", "search_knowledge", "unknown"],
            "tool_whitelist": ["http_api_call"],
            "default_models": {
                "classifier": {"provider": "groq", "model": "llama-3.1-8b-instant"},
                "executor": {"provider": "deepseek", "model": "deepseek-chat"},
            },
        },
    },
]

TEMPLATES = [
    {
        "pack_id": "tourism@1.0.0",
        "intent": "general_chat",
        "role": "system",
        "template_text": (
            "Bạn là trợ lý AI của {{ tenant_name }}, chuyên hỗ trợ khách du lịch.\n"
            "Ngày hôm nay: {{ today }}.\n"
            "{% if current_screen != 'không xác định' %}Khách đang ở màn hình: {{ current_screen }}.{% endif %}\n"
            "Trả lời thân thiện, ngắn gọn. Ưu tiên gợi ý dịch vụ của {{ tenant_name }}."
        ),
    },
    {
        "pack_id": "tourism@1.0.0",
        "intent": "api_action",
        "role": "system",
        "template_text": (
            "Bạn là trợ lý AI của {{ tenant_name }}, hỗ trợ đặt phòng và dịch vụ du lịch.\n"
            "Ngày hôm nay: {{ today }}.\n"
            "{% if business_rules %}Quy tắc nghiệp vụ: {{ business_rules }}{% endif %}\n"
            "Khi thực hiện thao tác: xác nhận với khách trước, sau đó mới gọi API."
        ),
    },
    {
        "pack_id": "generic@1.0.0",
        "intent": "general_chat",
        "role": "system",
        "template_text": (
            "Bạn là trợ lý AI thông minh của {{ tenant_name }}.\n"
            "Ngày hôm nay: {{ today }}.\n"
            "Hãy trả lời chính xác, ngắn gọn và hữu ích."
        ),
    },
    {
        "pack_id": "spa_booking@1.0.0",
        "intent": "general_chat",
        "role": "system",
        "template_text": (
            "Bạn là trợ lý AI của {{ tenant_name }}, chuyên tư vấn và đặt lịch spa/clinic.\n"
            "Ngày hôm nay: {{ today }}.\n"
            "Hãy tư vấn liệu trình phù hợp và hỗ trợ khách đặt lịch."
        ),
    },
    {
        "pack_id": "spa_booking@1.0.0",
        "intent": "api_action",
        "role": "system",
        "template_text": (
            "Bạn là trợ lý AI của {{ tenant_name }}, hỗ trợ đặt lịch spa/clinic.\n"
            "{% if business_rules %}Quy tắc: {{ business_rules }}{% endif %}\n"
            "Trước khi đặt lịch, xác nhận: tên khách, dịch vụ, ngày giờ mong muốn."
        ),
    },
]


async def seed():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("SET ROLE ai_admin")
    try:
        for pack in PACKS:
            await conn.execute(
                """
                INSERT INTO ai_service.industry_packs (pack_id, display_name, version, config)
                VALUES ($1, $2, $3, $4::jsonb)
                ON CONFLICT (pack_id) DO UPDATE
                SET display_name = EXCLUDED.display_name,
                    version = EXCLUDED.version,
                    config = EXCLUDED.config,
                    is_active = TRUE
                """,
                pack["pack_id"],
                pack["display_name"],
                pack["pack_id"].split("@")[1],
                json.dumps(pack["config"]),
            )
            print(f"✓ Pack: {pack['pack_id']}")

        for tmpl in TEMPLATES:
            await conn.execute(
                "UPDATE ai_service.prompt_templates SET is_active = FALSE WHERE pack_id=$1 AND intent=$2 AND role=$3",
                tmpl["pack_id"], tmpl["intent"], tmpl["role"],
            )
            row = await conn.fetchrow(
                "SELECT COALESCE(MAX(version),0) AS v FROM ai_service.prompt_templates WHERE pack_id=$1 AND intent=$2 AND role=$3",
                tmpl["pack_id"], tmpl["intent"], tmpl["role"],
            )
            await conn.execute(
                "INSERT INTO ai_service.prompt_templates (pack_id, intent, role, template_text, version) VALUES ($1,$2,$3,$4,$5)",
                tmpl["pack_id"], tmpl["intent"], tmpl["role"], tmpl["template_text"], row["v"] + 1,
            )
            print(f"  ✓ Template: {tmpl['pack_id']} / {tmpl['intent']}:{tmpl['role']}")

    finally:
        await conn.close()
        print("\nDone!")


asyncio.run(seed())