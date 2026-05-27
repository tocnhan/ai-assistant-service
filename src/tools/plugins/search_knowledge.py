# src/tools/plugins/search_knowledge.py
from src.tools.base import BaseTool
from src.services.qdrant_search import qdrant_search


class SearchKnowledgeTool(BaseTool):
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

    # sẽ được set bởi configure()
    collection: str = ""
    top_k_default: int = 5

    def configure(self, config: dict) -> "SearchKnowledgeTool":
        """
        config từ DB sẽ có dạng:
        {"collection": "abc123_docs", "top_k_default": 5}
        Nếu không có collection thì fallback về {company_guid}_docs
        — được set lúc load ở ToolPluginLoader.
        """
        instance = SearchKnowledgeTool()
        instance.collection = config.get("collection", "")
        instance.top_k_default = config.get("top_k_default", 5)
        return instance

    async def _run(self, query: str, top_k: int = None) -> dict:
        results = await qdrant_search(
            query=query,
            top_k=top_k or self.top_k_default,
            collection=self.collection or None,
        )
        return {"results": results, "count": len(results)}