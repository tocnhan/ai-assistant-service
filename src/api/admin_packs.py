# src/api/admin_packs.py
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from src.db.session import DatabasePool
from src.packs.loader import invalidate_pack_cache

router = APIRouter(prefix="/admin", tags=["admin"])


class CreatePackRequest(BaseModel):
    pack_id: str
    display_name: str
    config: dict


class AssignPackRequest(BaseModel):
    company_guid: str
    pack_id: str
    overrides: dict = {}


class UpsertTemplateRequest(BaseModel):
    pack_id: str
    intent: str
    role: str = "system"
    template_text: str


# ── CRUD Pack ────────────────────────────────────────────────────────────────

@router.post(
    "/packs",
    responses={400: {"description": "Pack ID đã tồn tại"}},
)
async def create_pack(body: CreatePackRequest):
    async with DatabasePool._pool.acquire() as conn:
        try:
            await conn.execute(
                """
                INSERT INTO ai_service.industry_packs (pack_id, display_name, config)
                VALUES ($1, $2, $3::jsonb)
                """,
                body.pack_id,
                body.display_name,
                json.dumps(body.config),
            )
        except Exception as e:
            if "unique" in str(e).lower():
                raise HTTPException(400, f"Pack '{body.pack_id}' đã tồn tại.")
            raise
    return {"ok": True, "pack_id": body.pack_id}


@router.get("/packs")
async def list_packs():
    async with DatabasePool._pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT pack_id, display_name, is_active, created_at FROM ai_service.industry_packs ORDER BY created_at DESC"
        )
    return [dict(r) for r in rows]


@router.delete("/packs/{pack_id}")
async def disable_pack(pack_id: str):
    async with DatabasePool._pool.acquire() as conn:
        await conn.execute(
            "UPDATE ai_service.industry_packs SET is_active = FALSE WHERE pack_id = $1",
            pack_id,
        )
    await invalidate_pack_cache(pack_id)
    return {"ok": True}


# ── Assign Pack cho Tenant ────────────────────────────────────────────────────

@router.post("/tenants/assign-pack")
async def assign_pack(body: AssignPackRequest):
    async with DatabasePool._pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO ai_service.tenant_pack_assignments (company_guid, pack_id, overrides)
            VALUES ($1::uuid, $2, $3::jsonb)
            ON CONFLICT (company_guid)
            DO UPDATE SET pack_id = EXCLUDED.pack_id, overrides = EXCLUDED.overrides
            """,
            body.company_guid,
            body.pack_id,
            json.dumps(body.overrides),
        )
    return {"ok": True}


# ── Prompt Template CRUD ──────────────────────────────────────────────────────

@router.post("/packs/templates")
async def upsert_template(body: UpsertTemplateRequest):
    async with DatabasePool._pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COALESCE(MAX(version), 0) AS max_ver
            FROM ai_service.prompt_templates
            WHERE pack_id = $1 AND intent = $2 AND role = $3
            """,
            body.pack_id, body.intent, body.role,
        )
        next_version = row["max_ver"] + 1

        await conn.execute(
            """
            UPDATE ai_service.prompt_templates SET is_active = FALSE
            WHERE pack_id = $1 AND intent = $2 AND role = $3
            """,
            body.pack_id, body.intent, body.role,
        )

        await conn.execute(
            """
            INSERT INTO ai_service.prompt_templates
              (pack_id, intent, role, template_text, version, is_active)
            VALUES ($1, $2, $3, $4, $5, TRUE)
            """,
            body.pack_id, body.intent, body.role,
            body.template_text, next_version,
        )

    await invalidate_pack_cache(body.pack_id)
    return {"ok": True, "version": next_version}


@router.get("/packs/{pack_id}/templates")
async def list_templates(pack_id: str):
    async with DatabasePool._pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT intent, role, version, is_active,
                   LEFT(template_text, 100) AS preview
            FROM ai_service.prompt_templates
            WHERE pack_id = $1
            ORDER BY intent, role, version DESC
            """,
            pack_id,
        )
    return [dict(r) for r in rows]