# src/packs/resolver.py
import json
from dataclasses import dataclass
from src.packs.loader import PackConfig, load_pack
from src.db.session import DatabasePool


@dataclass
class EffectiveConfig:
    pack_id: str
    intents: list[str]
    tool_whitelist: list[str]
    default_models: dict
    prompts: dict[str, str]


async def resolve_for_tenant(company_guid: str) -> EffectiveConfig:
    try:
        async with DatabasePool._pool.acquire() as conn:
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1::text, true)",
                str(company_guid),
            )
            row = await conn.fetchrow(
                """
                SELECT pack_id, overrides
                FROM ai_service.tenant_pack_assignments
                WHERE company_guid = $1::uuid
                """,
                company_guid,
            )
    except Exception as e:
        row = None

    if not row:
        pack = await load_pack("generic@1.0.0")
        return _to_effective(pack, overrides={})

    try:
        pack = await load_pack(row["pack_id"])
    except Exception:
        pack = await load_pack("generic@1.0.0")    
        
    overrides = row["overrides"] or {}
    if isinstance(overrides, str):
        overrides = json.loads(overrides)
    return _to_effective(pack, overrides)


def _to_effective(pack: PackConfig, overrides: dict) -> EffectiveConfig:
    intents = overrides.get("intents", pack.intents)

    tool_whitelist = list(set(pack.tool_whitelist) | set(overrides.get("extra_tools", [])))

    default_models = {**pack.default_models}
    for role, cfg in overrides.get("default_models", {}).items():
        default_models[role] = cfg

    prompts = {**pack.prompts}
    for key, template in overrides.get("prompts", {}).items():
        prompts[key] = template

    return EffectiveConfig(
        pack_id=pack.pack_id,
        intents=intents,
        tool_whitelist=tool_whitelist,
        default_models=default_models,
        prompts=prompts,
    )