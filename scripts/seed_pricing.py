# scripts/seed_pricing.py
import asyncio, sys, os
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncpg
from src.core.config import settings

PRICING = [
    ("gemini", "gemini-2.5-flash-lite", date(2025,1,1), 0.10,  0.40,  0.025),
    ("gemini", "gemini-2.5-flash",      date(2025,1,1), 0.30,  2.50,  0.075),
    ("gemini", "gemini-2.5-pro",        date(2025,1,1), 1.25, 10.00,  0.312),
    ("openai", "gpt-4o-mini",           date(2025,1,1), 0.15,  0.60,  0.075),
    ("openai", "gpt-4o",                date(2025,1,1), 2.50, 10.00,  1.250),
    ("anthropic", "claude-haiku-4-5",   date(2025,1,1), 0.80,  4.00,  0.080),
    ("anthropic", "claude-sonnet-4-6",  date(2025,1,1), 3.00, 15.00,  0.300),
    ("deepseek",  "deepseek-chat",              date(2026,1,1), 0.07,  1.10,  0.018),
    ("deepseek",  "deepseek-reasoner",          date(2026,1,1), 0.55,  2.19,  0.138),
    ("groq",      "llama-3.1-8b-instant",       date(2026,1,1), 0.05,  0.08,  0.000),
    ("groq",      "llama-3.3-70b-versatile",    date(2026,1,1), 0.59,  0.79,  0.000),
]

async def seed():
    conn = await asyncpg.connect(settings.DATABASE_ADMIN_URL)
    for p, m, d, i, o, c in PRICING:
        await conn.execute("""
            INSERT INTO ai_service.model_pricing
              (provider, model, effective_from,
               input_price_per_million, output_price_per_million,
               cached_price_per_million)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT DO NOTHING
        """, p, m, d, i, o, c)
    await conn.close()
    print("✓ Pricing seeded")

asyncio.run(seed())