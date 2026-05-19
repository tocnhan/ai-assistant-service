# src/services/usage_logger.py
import asyncio
import time
import structlog
from src.db.session import DatabasePool
from src.llm.pricing import calculate_cost

logger = structlog.get_logger()

async def log_usage(
    company_guid: str,
    user_guid: str,
    request_id: str,
    agent_name: str,
    provider: str,
    model: str,
    usage,
    latency_ms: int,
    success: bool = True,
    error_code: str = None,
):
    try:
        cost = await calculate_cost(provider, model, usage)

        # src/services/usage_logger.py — sửa phần INSERT
        async with DatabasePool._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.current_tenant', $1, TRUE)",
                    company_guid
                )
                await conn.execute("""
                    INSERT INTO ai_service.llm_usage_log
                    (company_guid, user_guid,
                    agent_name, provider, model,
                    prompt_tokens, output_tokens, cached_tokens,
                    thoughts_tokens, tool_tokens, total_tokens,
                    estimated_cost_usd, latency_ms, success, error_code)
                    VALUES
                    ($1::uuid, $2::uuid,
                    $3, $4, $5,
                    $6, $7, $8,
                    $9, $10, $11,
                    $12, $13, $14, $15)
                """,
                company_guid, user_guid,
                agent_name, provider, model,
                usage.prompt_tokens, usage.output_tokens, usage.cached_tokens,
                usage.thoughts_tokens, usage.tool_tokens, usage.total_tokens,
                cost, latency_ms, success, error_code
                )
        logger.info("usage.logged",
            provider=provider, model=model,
            total_tokens=usage.total_tokens,
            cost_usd=cost
        )

    except Exception as e:
        logger.error("usage.log_failed", error=str(e))


def log_usage_background(
    company_guid: str,
    user_guid: str,
    request_id: str,
    agent_name: str,
    provider: str,
    model: str,
    usage,
    latency_ms: int,
):
    """Gọi cái này trong endpoint — không block response."""
    asyncio.create_task(log_usage(
        company_guid=company_guid,
        user_guid=user_guid,
        request_id=request_id,
        agent_name=agent_name,
        provider=provider,
        model=model,
        usage=usage,
        latency_ms=latency_ms,
    ))