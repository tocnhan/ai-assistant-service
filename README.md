# BE AI Assistant Service

Backend microservice độc lập xử lý toàn bộ logic AI agent cho hệ thống quản lý du lịch.

**Multi-LLM Provider · Multi-Tenant · Production-Ready**

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

---

## Tổng quan

BE AI Service là một microservice riêng biệt, **không chia sẻ database với BE chính**. Mọi request đến từ BE Private đã được xác thực user, sau đó BE Private sign request bằng HMAC-SHA256 trước khi gửi sang AI Service.

```
FE → BE Private (auth user) → BE AI Service (HMAC verify → LLM → stream response)
```

Tính năng chính:
- **Multi-LLM provider**: Gemini, OpenAI, Anthropic, Groq, Ollama — swap bằng config, không sửa code
- **Multi-tenant với RLS**: database-level isolation, fail-closed by default
- **SSE streaming**: response stream từng token về FE
- **Quota management**: hard limit per tenant theo token/cost/request
- **Usage tracking**: log mọi LLM call với cost ước tính
- **Observability**: Langfuse trace, Prometheus metrics, structlog JSON

---

## Tech Stack

| Thành phần | Công nghệ |
|---|---|
| Language | Python 3.11+ |
| Web framework | FastAPI |
| Agent framework | Pydantic AI |
| Database | PostgreSQL 15 + TimescaleDB |
| Cache | Redis 7 |
| ORM / Migration | SQLAlchemy 2.0 + Alembic |
| Package manager | uv |
| Container | Docker + Docker Compose |

---

## Cấu trúc project

```
ai-assistant-service/
├── src/
│   ├── main.py                  # FastAPI app entry, lifespan, middleware
│   ├── api/
│   │   ├── chat.py              # POST /chat
│   │   └── health.py            # GET /health, /ready
│   ├── core/
│   │   └── config.py            # Settings từ .env (pydantic-settings)
│   ├── db/
│   │   └── session.py           # asyncpg pool + RLS tenant context
│   ├── llm/
│   │   ├── base.py              # LLMProvider abstract, dataclasses
│   │   ├── registry.py          # Provider registry
│   │   ├── pricing.py           # Cost calculator
│   │   └── providers/
│   │       ├── gemini.py
│   │       └── openai_provider.py
│   ├── middleware/
│   │   └── tenant.py            # HMAC verify + tenant context
│   └── services/
│       ├── audit.py             # Security event logger
│       └── usage_logger.py      # Async LLM usage logger
├── tests/
│   └── integration/
│       └── test_rls.py          # RLS isolation test
├── alembic/
│   └── versions/
│       └── f4e886f1f643_001_initial_schema.py
├── scripts/
│   ├── dev_setup.py             # Seed test data (chạy lần đầu)
│   ├── seed_pricing.py          # Seed LLM pricing
│   ├── seed_test_data.py        # Seed test tenant
│   └── gen_hmac.py              # Generate HMAC signature để test API
├── docker/
│   └── docker-compose.yml
├── conftest.py
├── pyproject.toml
├── .env.example
└── README.md
```

---

## Yêu cầu môi trường

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) — package manager
- Docker Desktop
- VS Code (khuyến nghị) với extensions: Python, Pylance, Docker, SQLTools, REST Client

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

Đợi containers healthy:

```bash
docker ps
# postgres: (healthy), redis: (healthy)
```

### 4. Tạo DB users và chạy migration

```bash
# Tạo roles (chỉ cần 1 lần)
docker exec -it docker-postgres-1 psql -U postgres -d ai_db -c "
  CREATE ROLE ai_admin LOGIN PASSWORD 'your-password' BYPASSRLS SUPERUSER;
  CREATE ROLE ai_app   LOGIN PASSWORD 'your-password';
  GRANT ALL ON DATABASE ai_db TO ai_admin;
  GRANT ALL ON SCHEMA public TO ai_admin;
"

# Chạy migration
uv run alembic upgrade head
```

### 5. Seed data lần đầu

```bash
uv run python scripts/dev_setup.py
```

### 6. Start app

```bash
uv run uvicorn src.main:app --reload
```

Mở `http://localhost:8000/docs` để xem Swagger UI.

---

## Chạy dev hàng ngày

```bash
# 1. Start Docker (data persist, không cần seed lại)
docker compose -f docker/docker-compose.yml up -d

# 2. Start app
uv run uvicorn src.main:app --reload
```

> **Lưu ý:** Chỉ chạy `dev_setup.py` lại nếu bạn đã chạy `docker compose down -v` (xóa volume).

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

# Security — HMAC shared secret với BE Private
HMAC_SECRET=change-this-in-production

# LLM Providers — điền cái nào đang dùng
GEMINI_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GROQ_API_KEY=
```

---

## API Overview

### Authentication

Mọi request (trừ `/health`, `/ready`) phải có headers:

| Header | Mô tả |
|---|---|
| `X-Company-GUID` | UUID của tenant |
| `X-User-GUID` | UUID của user |
| `X-Domain` | Domain của tenant |
| `X-Timestamp` | Unix timestamp (chống replay, window 5 phút) |
| `X-Signature` | HMAC-SHA256(secret, timestamp + body) |
| `X-Request-Id` | UUID để trace |

Generate signature để test:

```bash
uv run python scripts/gen_hmac.py
```

### Endpoints

| Method | Path | Mô tả |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `GET` | `/ready` | Readiness check |
| `POST` | `/chat` | Chat với AI (streaming SSE — Sprint 4) |

### POST /chat

Request:
```json
{
  "message": "Booking #1234 hôm nay có gì không?",
  "conversation_id": "optional-uuid",
  "intent_hint": "optional-bypass-classifier"
}
```

Response (hiện tại — non-streaming):
```json
{
  "response": "...",
  "request_id": "test-001",
  "company_guid": "550e8400-...",
  "usage": {
    "total_tokens": 106,
    "prompt_tokens": 2,
    "output_tokens": 104,
    "estimated_cost_usd": 0.0000416
  }
}
```

---

## Test

### Chạy tất cả tests

```bash
uv run pytest tests/ -v
```

### RLS isolation test (quan trọng nhất)

```bash
uv run pytest tests/integration/test_rls.py -v
```

Test này verify tenant B không đọc được data của tenant A — phải pass 100% trước khi deploy.

### Test API thủ công

```bash
# Generate HMAC signature
uv run python scripts/gen_hmac.py

# Chạy curl với signature vừa generate (Windows)
curl.exe -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Company-GUID: 550e8400-e29b-41d4-a716-446655440000" \
  -H "X-User-GUID: 660e8400-e29b-41d4-a716-446655440001" \
  -H "X-Domain: https://test.com" \
  -H "X-Timestamp: <TIMESTAMP>" \
  -H "X-Signature: <SIGNATURE>" \
  -H "X-Request-Id: test-001" \
  -d "@scripts/test_body.json"
```

### Verify usage log vào DB

```bash
docker exec -it docker-postgres-1 psql -U postgres -d ai_db -c \
  "SELECT agent_name, provider, model, total_tokens, estimated_cost_usd, latency_ms FROM ai_service.llm_usage_log LIMIT 5;"
```

---

## Kiến trúc bảo mật

### Defense in depth

```
Layer 1 (Network)   : HTTPS only, IP whitelist nếu có
Layer 2 (App)       : HMAC signature, anti-replay timestamp, tenant validation
Layer 3 (Database)  : Row-Level Security — ai_app không bypass được RLS
Layer 4 (LLM)       : tenant_id inject từ middleware, không từ LLM
Layer 5 (Audit)     : log mọi security event vào audit_log table
```

### Multi-tenant isolation

- Mỗi request set `SET LOCAL app.current_tenant = '<uuid>'` trong DB transaction
- RLS policy tự động filter tất cả queries — app code không cần WHERE company_guid
- `ai_app` role không có `BYPASSRLS` — không thể tắt RLS dù muốn

### HMAC verification

```python
signature = HMAC-SHA256(HMAC_SECRET, f"{timestamp}{request_body}")
```

- Timestamp window 5 phút — chống replay attack
- `hmac.compare_digest` — chống timing attack

---

## Roadmap

| Sprint | Tuần | Status |
|---|---|---|
| Sprint 1 — Foundation | 1-2 | ✅ Done |
| Sprint 2 — Security & LLM Adapter | 3-4 | ✅ Done |
| Sprint 3 — Agent Framework | 5-6 | 🔄 Next |
| Sprint 4 — Streaming & Quota | 7-8 | ⏳ Pending |
| Sprint 5 — Admin & Observability | 9-10 | ⏳ Pending |
| Sprint 6 — Polish & Production | 11-12 | ⏳ Pending |

### Sprint 3 — việc tiếp theo
- Setup Pydantic AI
- Implement Intent Classifier
- Implement Agent Orchestrator
- Implement Tool layer (Qdrant search, BE Public API)
- Conversation memory với Redis
- Migrate agent đầu tiên từ n8n

---

## Troubleshooting

### App không start được — `password authentication failed`
```bash
# Recreate ai_app role
docker exec -it docker-postgres-1 psql -U postgres -d ai_db -c \
  "CREATE ROLE ai_app LOGIN PASSWORD 'your-password';"
uv run alembic upgrade head
```

### Data mất sau restart
```bash
# Kiểm tra volume còn không
docker volume ls | grep postgres_data

# Seed lại nếu cần
uv run python scripts/dev_setup.py
```

### HMAC Invalid Signature
- Timestamp phải trong vòng 5 phút kể từ lúc generate
- Body phải giống hệt nhau (dùng `@scripts/test_body.json` thay vì inline `-d`)
- Chạy lại `uv run python scripts/gen_hmac.py` để generate mới

### `unrecognized configuration parameter app.current_tenant`
- Cần `SET LOCAL` trong transaction trước khi query
- Xem `src/db/session.py` — `acquire_with_tenant()`