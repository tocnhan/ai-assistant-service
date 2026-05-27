import json
import structlog
from src.db.session import DatabasePool

logger = structlog.get_logger()

async def log_audit_event(
    event_type: str,
    company_guid: str = None,
    details: dict = None,
    severity: str = "WARNING",
):
    try:
        async with DatabasePool._pool.acquire() as conn:
            async with conn.transaction():
                # Set tenant context trước khi INSERT — RLS cần cái này
                await conn.execute(
                    "SELECT set_config('app.current_tenant', $1::text, true)",
                    str(company_guid) if company_guid else "",
                )
                await conn.execute(
                    """
                    INSERT INTO ai_service.audit_log
                      (event_type, company_guid, severity, details)
                    VALUES ($1, $2::uuid, $3, $4::jsonb)
                    """,
                    event_type,
                    company_guid,
                    severity,
                    json.dumps(details or {}),
                )
    except Exception as e:
        logger.error("audit.log_failed", error=str(e))