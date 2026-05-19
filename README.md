# BE AI Assistant Service

Backend microservice độc lập xử lý toàn bộ logic AI agent — từ intent classification, multi-turn conversation, tool calling đến SSE streaming response.

**Multi-LLM Provider · Multi-Tenant · Streaming SSE · Production-Ready**

---

## Mục lục

- [Tổng quan](#tổng-quan)
- [Tech Stack](#tech-stack)
- [Cấu trúc project](#cấu-trúc-project)
- [Yêu cầu môi trường](#yêu-cầu-môi-trường)
- [Cài đặt lần đầu](#cài-đặt-lần-đầu)
- [Chạy dev hàng ngày](#chạy-dev-hàng-ngày)
- [Cấu hình `.env`](#cấu-hình-env)
- [API Overview](#api-overview)
- [Test](#test)
- [Kiến trúc bảo mật](#kiến-trúc-bảo-mật)
- [Roadmap](#roadmap)
- [Troubleshooting](#troubleshooting)

---

## Tổng quan

BE AI Service là một microservice riêng biệt, **không chia sẻ database với BE chính**. Mọi request đến từ BE Private đã được xác thực user, sau đó BE Private sign request bằng HMAC-SHA256 trước khi gửi sang AI Service.

```
FE → BE Private (auth user) → BE AI Service (HMAC verify → classify → stream response)
```

Tính năng hiện tại (Sprint 1-4):

- **Multi-LLM provider**: Gemini, OpenAI, Anthropic, DeepSeek, Groq — swap bằng 1 dòng config, không sửa code
- **Multi-tenant với RLS**: database-level isolation, fail-closed by default
- **SSE streaming**: response stream từng token về FE, time-to-first-token < 1.5s
- **Intent classifier**: tự động phân loại `general_chat`, `search_knowledge`, `api_action`, `summarize`
- **Multi-turn memory**: Redis sliding window 10 turn, TTL 24h per conversation
- **Tool system**: ToolRegistry, SearchTool, HttpApiCallTool — plugin architecture
- **Usage tracking**: log mọi LLM call với cost ước tính per tenant
- **Domain whitelist**: chống SSRF, kiểm tra allowed_domains per tenant

---

## Tech Stack

| Thành phần      | Công nghệ                         |
|-----------------|-----------------------------------|
| Language        | Python 3.11+                      |
| Web framework   | FastAPI                           |
| Agent framework | Pydantic AI                       |
| Database        | PostgreSQL 15 + TimescaleDB       |
| Cache / Memory  | Redis 7                           |
| Migration       | Alembic                           |
| Package manager | uv                                |
| Container       | Docker + Docker Compose           |
| LLM Tracing     | Langfuse (self-hosted, Sprint 8)  |

---

## Cấu trúc project

```
ai-assistant-service/
├── src/
│   ├── main.py                      # FastAPI app entry, lifespan, middleware
│   ├── agents/
│   │   ├── base.py                  # BaseAgent, run(), stream()
│   │   ├── classifier.py            # ClassifierAgent — intent classification
│   │   ├── orchestrator.py          # Orchestrator — classify → route → stream
│   │   └── registry.py              # AgentRegistry — map intent → executor
│   ├── api/
│   │   ├── chat.py                  # POST /chat, POST /chat/stream (SSE)
│   │   └── providers.py             # GET /providers
│   ├── cache/
│   │   └── redis_client.py          # Redis connection + get_redis()
│   ├── core/
│   │   └── config.py                # Settings từ .env (pydantic-settings)
│   ├── db/
│   │   └── session.py               # asyncpg pool + RLS tenant context
│   ├── llm/
│   │   ├── base.py                  # LLMProvider abstract, dataclasses
│   │   ├── registry.py              # Provider registry
│   │   ├── selector.py              # ModelSelector — role-based provider selection
│   │   ├── pricing.py               # Cost calculator
│   │   └── providers/
│   │       ├── gemini.py            # Gemini (generate + stream)
│   │       ├── openai_provider.py   # OpenAI (generate + stream)
│   │       ├── anthropic_provider.py# Anthropic (generate + stream)
│   │       ├── deepseek_provider.py # DeepSeek (inherit OpenAI)
│   │       └── groq_provider.py     # Groq (inherit OpenAI)
│   ├── memory/
│   │   └── conversation.py          # Redis sliding window memory
│   ├── middleware/
│   │   └── tenant.py                # Pure ASGI HMACMiddleware
│   ├── services/
│   │   ├── audit.py                 # Security event logger
│   │   ├── usage_logger.py          # Async LLM usage logger
│   │   └── qdrant_search.py         # Vector search stub (Sprint 5)
│   └── tools/
│       ├── base.py                  # BaseTool, ToolRegistry, whitelist
│       ├── http_api_call.py         # HttpApiCallTool — gọi external API
│       └── search_tool.py           # SearchTool — wrap Qdrant search
├── tests/
│   ├── integration/
│   │   └── test_rls.py              # RLS isolation test
│   └── unit/
│       ├── test_classifier.py       # 6 cases
│       ├── test_memory.py           # 5 cases
│       ├── test_tools.py            # 7 cases
│       ├── test_model_selector.py   # 5 cases
│       ├── test_hmac_middleware.py  # 4 cases
│       ├── test_openai_provider.py
│       ├── test_anthropic_provider.py
│       └── test_pricing_calc.py
├── alembic/
│   └── versions/
│       ├── f4e886f1f643_001_initial_schema.py
│       ├── 0689772182af_002_add_allowed_domains.py
│       └── 8b32f1048493_003_sprint3_schema.py
├── scripts/
│   ├── gen_hmac.py                  # Generate HMAC signature để test
│   ├── seed_pricing.py              # Seed LLM pricing (5 providers)
│   ├── seed_test_data.py            # Seed test tenant
│   ├── test_chat.py                 # Multi-turn automated test
│   └── check_usage.py              # Xem cost + usage từ DB
├── docker/
│   └── docker-compose.yml
├── conftest.py
├── pyproject.toml
└── README.md
```

---

## Yêu cầu môi trường

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) — package manager
- Docker Desktop
- Ít nhất 1 LLM API key (Gemini free tier đủ để dev)

---

## Cài đặt lần đầu

### 1. Clone và setup môi trường

```bash
git clone <repo-url>
cd ai-assistant-service

# Cài uv nếu chưa có
pip install uv

# Cài dependencies
uv sync
```

### 2. Tạo file `.env`

```bash
cp .env.example .env
```

Điền các giá trị vào `.env` (xem phần [Cấu hình `.env`](#cấu-hình-env)).

### 3. Start Docker containers

```bash
docker compose -f docker/docker-compose.yml up -d
```

### 4. Chạy migration

```bash
uv run alembic upgrade head
```

### 5. Seed pricing data

```bash
uv run python scripts/seed_pricing.py
uv run python scripts/seed_test_data.py
```

### 6. Start app

```bash
uv run uvicorn src.main:app --reload
```

Mở `http://localhost:8000/docs` để xem Swagger UI.

---

## Chạy dev hàng ngày

```bash
# 1. Start Docker
docker compose -f docker/docker-compose.yml up -d

# 2. Start app
uv run uvicorn src.main:app --reload
```

---

## Cấu hình `.env`

```env
# App
APP_ENV=development
LOG_LEVEL=INFO

# Database
DATABASE_URL=postgresql+asyncpg://ai_app:your-password@127.0.0.1/ai_db
DATABASE_ADMIN_URL=postgresql://ai_admin:your-password@127.0.0.1/ai_db

# Redis
REDIS_URL=redis://localhost:6379/0

# Security
HMAC_SECRET=<generate: openssl rand -hex 32>

# LLM Providers — điền ít nhất 1
GEMINI_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
DEEPSEEK_API_KEY=
GROQ_API_KEY=

# External
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
```

---

## API Overview

### Authentication

Mọi request (trừ `/health`, `/ready`, `/docs`) phải có headers:

| Header           | Mô tả                                        |
|------------------|----------------------------------------------|
| `X-Company-GUID` | UUID của tenant                              |
| `X-User-GUID`    | UUID của user                                |
| `X-Domain`       | Domain của tenant (phải có trong allowed_domains) |
| `X-Timestamp`    | Unix timestamp (window 5 phút)               |
| `X-Signature`    | HMAC-SHA256(secret, timestamp + body)        |
| `X-Request-Id`   | UUID để trace                                |

Generate signature để test:

```bash
uv run python scripts/gen_hmac.py
```

### Endpoints

| Method | Path           | Mô tả                               |
|--------|----------------|-------------------------------------|
| `GET`  | `/health`      | Liveness check                      |
| `GET`  | `/ready`       | Readiness check                     |
| `GET`  | `/providers`   | Danh sách LLM provider đang active  |
| `POST` | `/chat`        | Chat non-streaming (backward compat)|
| `POST` | `/chat/stream` | Chat SSE streaming                  |

### POST /chat

Request:
```json
{
  "message": "xin chào",
  "conversation_id": "conv-uuid-optional",
  "intent_hint": "general_chat"
}
```

Response:
```json
{
  "response": "Xin chào! Tôi có thể giúp gì cho bạn?",
  "request_id": "req-001",
  "provider": "gemini",
  "model": "gemini-2.5-flash",
  "usage": {
    "total_tokens": 58,
    "prompt_tokens": 10,
    "output_tokens": 48
  }
}
```

### POST /chat/stream (SSE)

Response stream — mỗi event là 1 dòng `data: {...}`:

```
data: {"type": "intent", "intent": "general_chat"}
data: {"type": "delta", "delta": "Xin"}
data: {"type": "delta", "delta": " chào!"}
data: {"type": "done", "request_id": "req-001", "latency_ms": 823, "usage": {...}}
```

Event types:

| Type    | Mô tả                                    |
|---------|------------------------------------------|
| `intent`| Intent đã classify được                  |
| `delta` | Token mới từ LLM                         |
| `done`  | Kết thúc, kèm latency + usage            |
| `error` | Lỗi trong quá trình xử lý               |

---

## Test

### Chạy unit tests

```bash
uv run pytest tests/unit/ -v
```

### RLS isolation test

```bash
uv run pytest tests/integration/test_rls.py -v
```

Test này verify tenant B không đọc được data của tenant A. **Phải pass 100% trước khi deploy.**

### Multi-turn conversation test

```bash
uv run python scripts/test_chat.py
```

Test 4 message liên tiếp với cùng `conversation_id` — verify memory hoạt động.

### Test API thủ công

```bash
# Bước 1: Sửa body test
# Windows
Set-Content -Path scripts/test_body.json -Value '{"message": "xin chao"}' -Encoding ascii

# Bước 2: Generate HMAC
uv run python scripts/gen_hmac.py

# Bước 3: Gọi stream endpoint
curl.exe -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -H "X-Company-GUID: <guid>" \
  -H "X-User-GUID: <user-guid>" \
  -H "X-Domain: <domain>" \
  -H "X-Timestamp: <timestamp>" \
  -H "X-Signature: <signature>" \
  -H "X-Request-Id: req-001" \
  -d "@scripts/test_body.json" --no-buffer
```

### Xem usage + cost

```bash
uv run python scripts/check_usage.py
```

---

## Kiến trúc bảo mật

```
Layer 1 (Network)  : HTTPS only
Layer 2 (App)      : HMAC-SHA256, anti-replay timestamp (5 phút), domain whitelist
Layer 3 (Database) : Row-Level Security — ai_app không bypass được RLS
Layer 4 (LLM)      : tenant_id inject từ middleware, không từ LLM output
Layer 5 (Audit)    : log mọi security event vào audit_log
```

### HMAC verification

```
signature = HMAC-SHA256(HMAC_SECRET, f"{timestamp}{request_body}")
```

- Timestamp window 5 phút — chống replay attack
- `hmac.compare_digest` — chống timing attack
- Pure ASGI middleware — compatible với SSE streaming

### Multi-tenant isolation

- RLS policy filter tự động tất cả queries theo `app.current_tenant`
- `ai_app` role không có `BYPASSRLS`
- `allowed_domains` table kiểm tra domain whitelist chống SSRF

---

## Multi-Provider Config

Đổi provider mặc định trong `src/llm/selector.py`:

```python
DEFAULT_MODELS = {
    "classifier": ("groq", "llama-3.1-8b-instant"),   # nhanh, rẻ
    "executor":   ("gemini", "gemini-2.5-flash"),      # balance
    "summarizer": ("deepseek", "deepseek-chat"),       # rẻ
    "premium":    ("anthropic", "claude-sonnet-4-6"),  # quality cao
}
```

Không cần restart — chỉ cần đảm bảo API key của provider đó có trong `.env`.

---

## Roadmap

| Sprint                               | Tuần  | Status         |
|--------------------------------------|-------|----------------|
| Sprint 1 — Foundation                | 1-2   | ✅ Done        |
| Sprint 2 — Security & LLM Adapter   | 3-4   | ✅ Done        |
| Sprint 3 — Tech Debt + 5 Providers  | 5-6   | ✅ Done        |
| Sprint 4 — Agent Runtime + SSE      | 7-8   | ✅ Done        |
| Sprint 5 — Industry Pack + Qdrant   | 9-10  | ⏳ Pending     |
| Sprint 6 — Credit Wallet            | 11-12 | ⏳ Pending     |
| Sprint 7 — BYOK + Tenant Override   | 13-14 | ⏳ Pending     |
| Sprint 8 — Observability + Prod     | 15-16 | ⏳ Pending     |

---

## Troubleshooting

### HMAC Invalid Signature

- Timestamp phải trong vòng 5 phút
- Body phải giống hệt lúc gen — dùng `@scripts/test_body.json`, không dùng inline `-d '{...}'`
- Chạy lại `uv run python scripts/gen_hmac.py`

### Domain not allowed

Tenant chưa có domain trong `allowed_domains`. Thêm vào DB:
```python
# Tạo file fix_domain.py và chạy
uv run python fix_domain.py
```

### Provider 503 / rate limit

Đổi provider trong `src/llm/selector.py` → đổi `executor` sang provider khác → restart app.

### Redis connection refused

```bash
docker compose -f docker/docker-compose.yml up -d
```

### Data mất sau restart

```bash
docker volume ls | grep postgres_data
uv run python scripts/seed_test_data.py
uv run python scripts/seed_pricing.py
```

### `unrecognized configuration parameter app.current_tenant`

Cần chạy `SET LOCAL` trong transaction. Xem `src/db/session.py`.