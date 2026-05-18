# test_llm.py
import asyncio
from src.llm.registry import LLMRegistry
from src.core.config import settings

async def main():
    LLMRegistry.register_all()
    
    # Dùng provider nào có API key
    provider_name = "gemini" if settings.GEMINI_API_KEY else "openai"
    provider = LLMRegistry.get(provider_name)
    
    model = "gemini-2.5-flash-lite" if provider_name == "gemini" else "gpt-4o-mini"
    
    response = await provider.generate(
        model=model,
        messages=[{"role": "user", "content": "m có thể làm những gì! Trả lời ngắn thôi."}]
    )
    print(f"Response: {response.text}")
    print(f"Tokens: {response.usage.total_tokens}")

asyncio.run(main())