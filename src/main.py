from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.core.config import settings
from src.db.session import DatabasePool
from src.llm.registry import LLMRegistry
from src.middleware.tenant import verify_hmac_middleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    await DatabasePool.init()
    LLMRegistry.register_all()
    yield
    await DatabasePool.close()

app = FastAPI(
    title="BE AI Assistant Service",
    lifespan=lifespan,
    docs_url="/docs" if settings.APP_ENV != "production" else None
)

app.middleware("http")(verify_hmac_middleware)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/ready")
async def ready():
    return {"status": "ready"}