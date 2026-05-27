# src/tools/plugins/web_search.py
import httpx
from src.tools.base import BaseTool


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Tìm kiếm thông tin trên internet. Dùng khi user hỏi thông tin thời sự, giá cả, thông tin không có trong KB."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Câu truy vấn tìm kiếm",
            },
        },
        "required": ["query"],
    }

    api_key: str = ""
    max_results: int = 5

    def configure(self, config: dict) -> "WebSearchTool":
        instance = WebSearchTool()
        instance.api_key = config.get("api_key", "")
        instance.max_results = config.get("max_results", 5)
        return instance

    async def _run(self, query: str) -> dict:
        if not self.api_key:
            return {"error": "web_search chưa được cấu hình api_key."}

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"query": query, "max_results": self.max_results},
            )
            data = response.json()
            return {
                "results": data.get("results", []),
                "count": len(data.get("results", [])),
            }