from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # Database — bắt buộc set trong .env, không có default chứa credential
    DATABASE_URL: str = ""
    DATABASE_ADMIN_URL: str = ""

    REDIS_URL: str = "redis://localhost:6379/0"

    # Security
    HMAC_SECRET: str = "change-this-in-production"

    # LLM Providers
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    DEEPSEEK_API_KEY: str | None = None
    GROQ_API_KEY: str = ""

    # External services
    BE_PUBLIC_BASE_URL: str = ""
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""

    # Langfuse
    LANGFUSE_HOST: str = ""
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()