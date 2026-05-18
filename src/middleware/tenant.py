import hmac as hmac_lib
import hashlib
import time
import json
from fastapi import Request
from fastapi.responses import JSONResponse
from src.core.config import settings
from src.db.session import DatabasePool
from src.services.audit import log_audit_event

SKIP_PATHS = {"/health", "/ready", "/docs", "/openapi.json", "/redoc"}

async def verify_hmac_middleware(request: Request, call_next):
    if request.url.path in SKIP_PATHS:
        return await call_next(request)

    signature    = request.headers.get("X-Signature")
    timestamp    = request.headers.get("X-Timestamp")
    company_guid = request.headers.get("X-Company-GUID")
    user_guid    = request.headers.get("X-User-GUID")
    domain       = request.headers.get("X-Domain")
    request_id   = request.headers.get("X-Request-Id", "")

    if not all([signature, timestamp, company_guid, user_guid, domain]):
        return JSONResponse(status_code=401, content={
            "error": {"code": "MISSING_HEADERS", "message": "Required headers missing"}
        })

    try:
        ts = int(timestamp)
        if abs(int(time.time()) - ts) > 300:
            await log_audit_event("TIMESTAMP_EXPIRED", company_guid)
            return JSONResponse(status_code=401, content={
                "error": {"code": "TIMESTAMP_EXPIRED", "message": "Request quá cũ"}
            })
    except ValueError:
        return JSONResponse(status_code=401, content={
            "error": {"code": "INVALID_TIMESTAMP"}
        })

    body = await request.body()
    body_str = body.decode()

    # DEBUG
    import structlog
    logger = structlog.get_logger()
    logger.info("hmac_debug",
        secret=repr(settings.HMAC_SECRET),
        input_str=repr(f"{timestamp}{body_str}"),
        expected=hmac_lib.new(
            settings.HMAC_SECRET.encode(),
            f"{timestamp}{body_str}".encode(),
            hashlib.sha256
        ).hexdigest(),
        received=repr(signature)
    )
    expected = hmac_lib.new(
        settings.HMAC_SECRET.encode(),
        f"{timestamp}{body.decode()}".encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac_lib.compare_digest(expected, signature):
        await log_audit_event("HMAC_FAIL", company_guid)
        return JSONResponse(status_code=401, content={
            "error": {"code": "INVALID_SIGNATURE", "message": "HMAC không hợp lệ"}
        })

    tenant = await _get_tenant(company_guid)
    if not tenant or tenant["status"] != "active":
        return JSONResponse(status_code=403, content={
            "error": {"code": "INVALID_TENANT", "message": "Tenant không tồn tại"}
        })

    request.state.company_guid = company_guid
    request.state.user_guid    = user_guid
    request.state.domain       = domain
    request.state.request_id   = request_id
    request.state.tenant       = dict(tenant)

    return await call_next(request)


async def _get_tenant(company_guid: str):
    async with DatabasePool._pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM ai_service.tenants WHERE company_guid = $1::uuid",
            company_guid
        )