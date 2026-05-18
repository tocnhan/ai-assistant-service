# src/llm/pricing.py
from src.db.session import DatabasePool

async def calculate_cost(provider: str, model: str, usage) -> float:
    try:
        async with DatabasePool._pool.acquire() as conn:
            pricing = await conn.fetchrow("""
                SELECT input_price_per_million,
                       output_price_per_million,
                       cached_price_per_million
                FROM ai_service.model_pricing
                WHERE provider = $1 AND model = $2
                  AND effective_from <= CURRENT_DATE
                  AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
                ORDER BY effective_from DESC
                LIMIT 1
            """, provider, model)

        if not pricing:
            return 0.0

        input_cost  = (usage.prompt_tokens - usage.cached_tokens) \
                      * pricing["input_price_per_million"] / 1_000_000
        cached_cost = usage.cached_tokens \
                      * (pricing["cached_price_per_million"] or 0) / 1_000_000
        output_cost = (usage.output_tokens + usage.thoughts_tokens) \
                      * pricing["output_price_per_million"] / 1_000_000

        return round(input_cost + cached_cost + output_cost, 8)

    except Exception:
        return 0.0