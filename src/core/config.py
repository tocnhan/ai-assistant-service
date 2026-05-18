from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env")

    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    DATABASE_URL: str = "postgresql+asyncpg://ai_app:Yyhl_20062023@127.0.0.1/ai_db"
    DATABASE_ADMIN_URL: str = "postgresql://ai_admin:Yyhl_20062023@127.0.0.1/ai_db"
    REDIS_URL: str = "redis://localhost:6379/0"
    HMAC_SECRET: str = "change-this-in-production"
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()