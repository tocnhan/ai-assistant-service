# src/tools/http_api_call.py
import httpx
from src.tools.base import BaseTool, ToolRegistry


class HttpApiCallTool(BaseTool):
    name = "http_api_call"
    description = "Gọi HTTP API của hệ thống. Dùng để thực hiện các thao tác booking, tạo đơn, cập nhật dữ liệu."
    input_schema = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "PATCH"],
                "description": "HTTP method",
            },
            "path": {
                "type": "string",
                "description": "API path, ví dụ: /api/bookings hoặc /api/orders/123",
            },
            "body": {
                "type": "object",
                "description": "Request body cho POST/PUT/PATCH",
            },
        },
        "required": ["method", "path"],
    }

    def __init__(self, base_url: str, headers: dict = None, timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout

    async def _run(self, method: str, path: str, body: dict = None, tenant_id: str = None) -> dict:
        # tenant_id inject từ middleware, KHÔNG để LLM tự sinh
        url = f"{self.base_url}{path}"
        headers = {**self.headers}
        if tenant_id:
            headers["X-Tenant-Id"] = tenant_id

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.request(
                method=method,
                url=url,
                json=body,
                headers=headers,
            )
            return {
                "status_code": response.status_code,
                "data": response.json() if response.content else {},
                "success": response.is_success,
            }


# Register mặc định (base_url lấy từ config khi app start)
def register_http_tool(base_url: str, headers: dict = None):
    ToolRegistry.register(HttpApiCallTool(base_url=base_url, headers=headers))