# src/services/qdrant_search.py
from src.core.config import settings


async def qdrant_search(query: str, top_k: int = 5, collection: str = None) -> list[dict]:
    """
    Tìm kiếm vector trong Qdrant.
    Sprint 4: stub trả empty list nếu Qdrant chưa setup.
    Sprint 5: implement embedding + search thật.
    """
    if not settings.QDRANT_URL:
        return []

    try:
        from qdrant_client import AsyncQdrantClient
        from qdrant_client.models import SearchRequest

        client = AsyncQdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY or None,
        )

        # Sprint 4 stub — chưa có embedding model
        # Sprint 5 sẽ replace bằng embed query trước rồi mới search
        return []

    except Exception:
        return []