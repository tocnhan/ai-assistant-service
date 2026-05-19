# src/tools/search_tool.py
from src.tools.base import BaseTool, ToolRegistry
from src.services.qdrant_search import qdrant_search


class SearchTool(BaseTool):
    name = "search_knowledge"
    description = "Tìm kiếm thông tin trong knowledge base. Dùng khi user hỏi về sản phẩm, chính sách, thông tin doanh nghiệp."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Câu truy vấn tìm kiếm",
            },
            "top_k": {
                "type": "integer",
                "description": "Số kết quả trả về, mặc định 5",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    async def execute(self, query: str, top_k: int = 5, collection: str = None) -> dict:
        results = await qdrant_search(query=query, top_k=top_k, collection=collection)
        return {"results": results, "count": len(results)}


# Register
ToolRegistry.register(SearchTool())