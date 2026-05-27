# src/tools/plugins/http_api_call.py
import httpx
from src.tools.base import BaseTool


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

    # default — sẽ bị override bởi configure()
    base_url: str = ""
    headers: dict = {}
    timeout: int = 10

    def configure(self, config: dict) -> "HttpApiCallTool":
        """
        Inject config từ tenant_tool_configs.config.
        Tạo instance mới, không mutate instance gốc trong registry.
        """
        instance = HttpApiCallTool()
        instance.base_url = config.get("base_url", "").rstrip("/")
        instance.headers = config.get("headers", {})
        instance.timeout = config.get("timeout", 10)
        return instance

    async def _run(
        self,
        method: str,
        path: str,
        body: dict = None,
        tenant_id: str = None,
    ) -> dict:
        if not self.base_url:
            return {"error": "http_api_call chưa được cấu hình base_url cho tenant này."}

        url = f"{self.base_url}{path}"
        headers = {**self.headers}

        # tenant_id inject từ middleware, KHÔNG để LLM tự sinh
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