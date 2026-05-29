import hmac as hmac_lib
import hashlib
import time
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.requests import Request
from starlette.responses import JSONResponse
from src.core.config import settings
from src.db.session import DatabasePool
from src.services.audit import log_audit_event

SKIP_PATHS = {"/health", "/ready", "/docs", "/openapi.json", "/redoc", "/metrics"}


class HMACMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)

        if request.url.path in SKIP_PATHS:
            await self.app(scope, receive, send)
            return

        error = await self._verify(request)
        if error:
            await error(scope, receive, send)
            return

        body_bytes = request.scope["_body"]
        consumed = False

        async def cached_receive():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": body_bytes, "more_body": False}
            # Sau lần đầu → chờ disconnect
            return await receive()

        await self.app(scope, cached_receive, send)

    async def _verify(self, request: Request):
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

        body_bytes = await request.body()
        body_str = body_bytes.decode()

        expected = hmac_lib.new(
            settings.HMAC_SECRET.encode(),
            f"{timestamp}{body_str}".encode(),
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

        allowed = False
        if domain:
            async with DatabasePool._pool.acquire() as conn:
                allowed = await conn.fetchval(
                    """SELECT EXISTS(
                        SELECT 1 FROM ai_service.allowed_domains
                        WHERE company_guid = $1::uuid
                        AND LOWER(RTRIM(domain, '/')) = LOWER(RTRIM($2, '/'))
                        AND is_active = TRUE
                    )""",
                    company_guid, domain
                )
        if not allowed:
            await log_audit_event("DOMAIN_NOT_ALLOWED", company_guid)
            return JSONResponse(status_code=403, content={
                "error": {"code": "DOMAIN_NOT_ALLOWED", "message": f"Domain '{domain}' không được phép"}
            })

        # Set state vào scope
        request.state.company_guid = company_guid
        request.state.user_guid    = user_guid
        request.state.domain       = domain
        request.state.request_id   = request_id
        request.state.tenant       = dict(tenant)

        request.scope["_body"] = body_bytes
        return None


async def _get_tenant(company_guid: str):
    async with DatabasePool._pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM ai_service.tenants WHERE company_guid = $1::uuid",
            company_guid
        )