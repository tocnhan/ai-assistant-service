# src/api/admin_tools.py
import json
import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from src.db.session import DatabasePool

logger = structlog.get_logger()
router = APIRouter(prefix="/admin", tags=["admin-tools"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class TenantToolConfigUpsert(BaseModel):
    is_enabled: bool = True
    config: dict = {}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/tools")
async def list_tool_definitions():
    async with DatabasePool._pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT tool_name, display_name, description,
                   plugin_class, config_schema, input_schema, is_active
            FROM ai_service.tool_definitions
            ORDER BY tool_name
            """
        )
    
    tools = []
    for r in rows:
        tool = dict(r)
        # asyncpg trả JSONB dạng string — parse lại thành object
        if isinstance(tool["config_schema"], str):
            tool["config_schema"] = json.loads(tool["config_schema"])
        if isinstance(tool["input_schema"], str):
            tool["input_schema"] = json.loads(tool["input_schema"])
        tools.append(tool)

    return {"tools": tools, "total": len(tools)}

@router.get("/tenants/{company_guid}/tools")
async def get_tenant_tools(company_guid: str):
    async with DatabasePool._pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1::text, true)",
                str(company_guid),
            )
            rows = await conn.fetch(
                """
                SELECT
                    td.tool_name,
                    td.display_name,
                    td.description,
                    td.config_schema,
                    ttc.is_enabled,
                    ttc.config,
                    ttc.updated_at
                FROM ai_service.tool_definitions td
                LEFT JOIN ai_service.tenant_tool_configs ttc
                    ON td.tool_name = ttc.tool_name
                    AND ttc.company_guid = $1::uuid
                WHERE td.is_active = TRUE
                ORDER BY td.tool_name
                """,
                company_guid,
            )

    result = []
    for r in rows:
        config_schema = r["config_schema"]
        if isinstance(config_schema, str):
            config_schema = json.loads(config_schema)
        result.append({
            "tool_name": r["tool_name"],
            "display_name": r["display_name"],
            "description": r["description"],
            "config_schema": config_schema,
            "is_enabled": r["is_enabled"],
            "config": r["config"] or {},
            "updated_at": str(r["updated_at"]) if r["updated_at"] else None,
        })

    return {"company_guid": company_guid, "tools": result}


@router.put("/tenants/{company_guid}/tools/{tool_name}")
async def upsert_tenant_tool_config(
    company_guid: str,
    tool_name: str,
    body: TenantToolConfigUpsert,
):
    async with DatabasePool._pool.acquire() as conn:
        # Kiểm tra tool tồn tại
        exists = await conn.fetchval(
            "SELECT 1 FROM ai_service.tool_definitions WHERE tool_name = $1",
            tool_name,
        )
        if not exists:
            raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' không tồn tại.")

        # Dùng 1 transaction — set_config và INSERT cùng scope
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1::text, true)",
                str(company_guid),
            )
            await conn.execute(
                """
                INSERT INTO ai_service.tenant_tool_configs
                    (company_guid, tool_name, is_enabled, config)
                VALUES
                    ($1::uuid, $2, $3, $4::jsonb)
                ON CONFLICT (company_guid, tool_name) DO UPDATE SET
                    is_enabled = EXCLUDED.is_enabled,
                    config     = EXCLUDED.config,
                    updated_at = NOW()
                """,
                company_guid,
                tool_name,
                body.is_enabled,
                json.dumps(body.config),
            )

    logger.info(
        "admin.tool_config.upserted",
        company_guid=company_guid,
        tool_name=tool_name,
        is_enabled=body.is_enabled,
    )

    return {
        "company_guid": company_guid,
        "tool_name": tool_name,
        "is_enabled": body.is_enabled,
        "config": body.config,
        "status": "ok",
    }

@router.delete("/tenants/{company_guid}/tools/{tool_name}")
async def delete_tenant_tool_config(company_guid: str, tool_name: str):
    """
    Xóa config tool của tenant — tool sẽ về trạng thái default.
    """
    async with DatabasePool._pool.acquire() as conn:
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1::text, true)",
            company_guid,
        )
        result = await conn.execute(
            """
            DELETE FROM ai_service.tenant_tool_configs
            WHERE company_guid = $1::uuid AND tool_name = $2
            """,
            company_guid,
            tool_name,
        )

    deleted = result.split()[-1] != "0"
    return {
        "company_guid": company_guid,
        "tool_name": tool_name,
        "deleted": deleted,
    }

@router.get("/tenants/{company_guid}/tools/mcp-spec")
async def get_mcp_spec(company_guid: str):
    """
    Export danh sách tool theo chuẩn MCP JSON Schema.
    LLM client dùng cái này để biết tool nào available + cách gọi.
    Chỉ trả về tool đã enabled cho tenant này.
    """
    async with DatabasePool._pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1::text, true)",
                str(company_guid),
            )
            rows = await conn.fetch(
                """
                SELECT
                    td.tool_name,
                    td.description,
                    td.input_schema,
                    ttc.is_enabled
                FROM ai_service.tool_definitions td
                LEFT JOIN ai_service.tenant_tool_configs ttc
                    ON td.tool_name = ttc.tool_name
                    AND ttc.company_guid = $1::uuid
                WHERE td.is_active = TRUE
                ORDER BY td.tool_name
                """,
                company_guid,
            )

    tools = []
    for r in rows:
        # Chỉ include tool đã explicitly enabled
        # is_enabled = null nghĩa là chưa config → bỏ qua
        if not r["is_enabled"]:
            continue

        input_schema = r["input_schema"]
        if isinstance(input_schema, str):
            input_schema = json.loads(input_schema)

        # Chuẩn MCP tool spec
        tools.append({
            "name": r["tool_name"],
            "description": r["description"],
            "input_schema": input_schema,
        })

    return {
        "schema_version": "mcp-1.0",
        "company_guid": company_guid,
        "tools": tools,
        "total": len(tools),
    }