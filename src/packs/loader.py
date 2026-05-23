# src/packs/loader.py
import json
from dataclasses import dataclass, field
from src.db.session import DatabasePool
from src.cache.redis_client import get_redis

CACHE_TTL = 300  # 5 phút


@dataclass
class PackConfig:
    pack_id: str
    display_name: str
    intents: list[str]
    tool_whitelist: list[str]
    default_models: dict
    prompts: dict[str, str] = field(default_factory=dict)


async def load_pack(pack_id: str) -> PackConfig:
    cache_key = f"pack:{pack_id}"
    redis = get_redis()

    cached = await redis.get(cache_key)
    if cached:
        return _dict_to_pack(json.loads(cached))

    async with DatabasePool._pool.acquire() as conn:
        pack_row = await conn.fetchrow(
            """
            SELECT pack_id, display_name, config
            FROM ai_service.industry_packs
            WHERE pack_id = $1 AND is_active = TRUE
            """,
            pack_id,
        )
        if not pack_row:
            raise ValueError(f"Pack '{pack_id}' không tồn tại hoặc đã bị disable.")

        template_rows = await conn.fetch(
            """
            SELECT intent, role, template_text, version
            FROM ai_service.prompt_templates
            WHERE pack_id = $1 AND is_active = TRUE
            ORDER BY intent, role, version DESC
            """,
            pack_id,
        )

    config = pack_row["config"] or {}
    if isinstance(config, str):
        config = json.loads(config)
    prompts = {}
    seen = set()
    for row in template_rows:
        key = f"{row['intent']}:{row['role']}"
        if key not in seen:
            prompts[key] = row["template_text"]
            seen.add(key)

    pack_data = {
        "pack_id": pack_row["pack_id"],
        "display_name": pack_row["display_name"] or pack_row["pack_id"],
        "intents": config.get("intents", ["general_chat", "unknown"]),
        "tool_whitelist": config.get("tool_whitelist", []),
        "default_models": config.get("default_models", {}),
        "prompts": prompts,
    }

    await redis.setex(cache_key, CACHE_TTL, json.dumps(pack_data, ensure_ascii=False))
    return _dict_to_pack(pack_data)


async def invalidate_pack_cache(pack_id: str):
    await get_redis().delete(f"pack:{pack_id}")


def _dict_to_pack(data: dict) -> PackConfig:
    return PackConfig(
        pack_id=data["pack_id"],
        display_name=data["display_name"],
        intents=data["intents"],
        tool_whitelist=data["tool_whitelist"],
        default_models=data["default_models"],
        prompts=data["prompts"],
    )