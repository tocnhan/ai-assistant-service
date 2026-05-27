# src/services/tool_logger.py
import asyncio
import json
import structlog
from src.db.session import DatabasePool

logger = structlog.get_logger()


async def log_tool_call(
    company_guid: str,
    conversation_id: str | None,
    request_id: str | None,
    agent_name: str,
    tool_name: str,
    input_data: dict,
    output_data: dict,
    latency_ms: int,
    success: bool = True,
    error_message: str | None = None,
):
    try:
        async with DatabasePool._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.current_tenant', $1, TRUE)",
                    company_guid,
                )
                await conn.execute(
                    """
                    INSERT INTO ai_service.tool_call_log
                    (company_guid, conversation_id, request_id,
                     agent_name, tool_name,
                     input_data, output_data,
                     latency_ms, success, error_message)
                    VALUES
                    ($1::uuid, $2::uuid, $3::uuid,
                     $4, $5,
                     $6::jsonb, $7::jsonb,
                     $8, $9, $10)
                    """,
                    company_guid,
                    conversation_id,
                    request_id,
                    agent_name,
                    tool_name,
                    json.dumps(input_data),
                    json.dumps(output_data),
                    latency_ms,
                    success,
                    error_message,
                )
        logger.info("tool.logged", tool=tool_name, success=success, latency_ms=latency_ms)
    except Exception as e:
        logger.error("tool.log_failed", error=str(e))


def log_tool_call_background(**kwargs):
    """Fire-and-forget, không block response."""
    async with asyncio.TaskGroup() as tg:
        tg.create_task(log_tool_call(**kwargs))