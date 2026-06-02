# BE AI Assistant Service

Backend microservice độc lập xử lý toàn bộ logic AI agent — từ intent classification, multi-turn conversation, tool calling đến SSE streaming response.

**Multi-LLM Provider · Multi-Tenant · Industry Pack · Tool Plugin Architecture · Streaming SSE · Credit Wallet · Observability · Production-Ready**

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
- [Tool Plugin System](#tool-plugin-system)
- [Credit Wallet System](#credit-wallet-system)
- [Observability](#observability)
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

Tính năng hiện tại (Sprint 1-8):

- **Multi-LLM provider**: Gemini, OpenAI, Anthropic, DeepSeek, Groq — swap bằng 1 dòng config, không sửa code
- **Multi-tenant với RLS**: database-level isolation, fail-closed by default
- **Industry Pack System**: mỗi vertical là 1 pack versioned (tourism, generic, spa_booking...) — onboard khách mới chỉ cần assign pack, không cần code
- **Prompt Template Engine**: Jinja2 templates lưu DB, versioned, render runtime với context inject — đổi prompt không redeploy
- **SSE streaming**: response stream từng token về FE, time-to-first-token < 1.5s
- **Intent classifier**: tự động phân loại intent theo pack config (general_chat, search_knowledge, api_action, summarize...)
- **Multi-turn memory**: Redis sliding window 10 turn, TTL 24h per conversation
- **Tool Plugin Architecture**: dynamic plugin loading từ filesystem, config per-tenant từ DB, MCP-compatible spec export
- **KB Multi-tenant**: Qdrant collection routing theo tenant (`{company_guid}_docs`), không chia sẻ KB giữa các tenant
- **Credit Wallet**: ví credit thay quota cứng, atomic debit chống race condition (FOR UPDATE), markup configurable, monthly grant + reconcile job
- **Observability**: Prometheus metrics tại `/metrics`, Langfuse tracing mọi LLM call (prompt, token, latency, cost)
- **Usage tracking**: log mọi LLM call với cost ước tính per tenant
- **Domain whitelist**: chống SSRF, kiểm tra allowed_domains per tenant

---

## Tech Stack

| Thành phần      | Công nghệ                                     |
|-----------------|------------------------------------------------|
| Language        | Python 3.11+                                   |
| Web framework   | FastAPI                                        |
| Agent framework | Pydantic AI                                    |
| Database        | PostgreSQL 15 + TimescaleDB                    |
| Cache / Memory  | Redis 7                                        |
| Vector DB       | Qdrant                                         |
| Template Engine | Jinja2                                         |
| Migration       | Alembic                                        |
| Package manager | uv                                             |
| Container       | Docker + Docker Compose                        |
| Metrics         | Prometheus (prometheus-fastapi-instrumentator)  |
| LLM Tracing     | Langfuse (Cloud)                               |
| Scheduler       | APScheduler (monthly grant + reconcile)         |

---

## Cấu trúc project

```
ai-assistant-service/
├── src/
│   ├── main.py                          # FastAPI app entry, lifespan, middleware
│   ├── agents/
│   │   ├── base.py                      # BaseAgent, run(), stream()
│   │   ├── classifier.py                # ClassifierAgent — intent classification
│   │   ├── orchestrator.py              # Orchestrator — load pack → classify → load tools → stream
│   │   └── registry.py                  # AgentRegistry — map intent → executor
│   ├── api/
│   │   ├── chat.py                      # POST /chat, POST /chat/stream (SSE)
│   │   ├── providers.py                 # GET /providers
│   │   ├── admin_packs.py              # Admin: CRUD pack, assign tenant, upsert template
│   │   ├── admin_tools.py              # Admin: CRUD tool config per-tenant, MCP spec export
│   │   ├── admin_wallet.py             # Admin: wallet topup, grant, usage, anomalies
│   │   └── tenant_wallet.py            # Tenant: self-serve wallet, usage, transactions
│   ├── cache/
│   │   └── redis_client.py              # Redis connection + get_redis()
│   ├── core/
│   │   └── config.py                    # Settings từ .env (pydantic-settings)
│   ├── db/
│   │   └── session.py                   # asyncpg pool + RLS tenant context
│   ├── llm/
│   │   ├── base.py                      # LLMProvider abstract, dataclasses
│   │   ├── registry.py                  # Provider registry
│   │   ├── selector.py                  # ModelSelector — role-based provider selection
│   │   ├── pricing.py                   # Cost calculator
│   │   └── providers/
│   │       ├── gemini.py                # + Langfuse tracing
│   │       ├── openai_provider.py       # + Langfuse wrapper (auto-cover Groq/DeepSeek)
│   │       ├── anthropic_provider.py    # + Langfuse tracing
│   │       ├── deepseek_provider.py
│   │       └── groq_provider.py
│   ├── memory/
│   │   └── conversation.py              # Redis sliding window memory
│   ├── middleware/
│   │   └── tenant.py                    # Pure ASGI HMACMiddleware
│   ├── packs/
│   │   ├── loader.py                    # Load pack từ DB, cache Redis 5 phút
│   │   ├── resolver.py                  # Merge pack default + tenant override → EffectiveConfig
│   │   └── template_engine.py           # Jinja2 render prompt với context inject
│   ├── services/
│   │   ├── audit.py                     # Security event logger
│   │   ├── usage_logger.py              # Async LLM usage logger
│   │   ├── tool_config.py              # Load + configure tools per-tenant từ DB
│   │   ├── wallet.py                   # WalletService: check_balance, debit, credit, grant_monthly
│   │   ├── wallet_gate.py             # WalletGate: check trước / debit sau mỗi LLM call
│   │   ├── scheduler.py               # APScheduler: monthly_grant_job + reconcile_job
│   │   └── qdrant_search.py            # Vector search
│   └── tools/
│       ├── base.py                      # BaseTool, ToolRegistry, configure(), to_mcp_spec()
│       ├── loader.py                    # ToolPluginLoader — dynamic discover + register
│       └── plugins/
│           ├── __init__.py
│           ├── http_api_call.py         # Gọi external HTTP API per-tenant
│           ├── search_knowledge.py      # Qdrant vector search, collection per-tenant
│           └── web_search.py            # Web search qua Tavily API
├── tests/
│   ├── integration/
│   │   ├── test_rls.py                  # RLS isolation test
│   │   └── test_domain_check.py         # Domain whitelist test
│   ├── security/
│   │   └── test_security.py             # Cross-tenant, HMAC replay, SSRF tests
│   └── unit/
│       ├── test_packs.py
│       ├── test_classifier.py
│       ├── test_memory.py
│       ├── test_tools.py
│       ├── test_wallet.py               # Credit wallet unit tests
│       ├── test_model_selector.py
│       ├── test_hmac_middleware.py
│       ├── test_openai_provider.py
│       ├── test_anthropic_provider.py
│       └── test_pricing_calc.py
├── alembic/
│   └── versions/
│       ├── f4e886f1f643_001_initial_schema.py
│       ├── 0689772182af_002_add_allowed_domains.py
│       ├── 8b32f1048493_003_sprint3_schema.py
│       ├── 5228d1a84c24_004_sprint5_prompt_templates.py
│       ├── d365ee120fbf_006_sprint6_tool_plugin.py
│       └── 9d9c0f8331ef_007_sprint7_credit_wallet.py
├── scripts/
│   ├── gen_hmac.py                      # Generate HMAC signature để test
│   ├── seed_pricing.py                  # Seed LLM pricing (5 providers)
│   ├── seed_test_data.py                # Seed test tenant
│   ├── seed_packs.py                    # Seed 3 industry packs + prompt templates
│   ├── seed_tool_definitions.py         # Seed tool definitions vào DB
│   ├── check_tables.py                  # Kiểm tra bảng DB
│   ├── check_domains.py                 # Kiểm tra allowed_domains
│   ├── check_usage.py                   # Xem cost + usage từ DB
│   └── test_body.json                   # Body mẫu để test API
├── INCIDENT_RUNBOOK.md                  # Xử lý sự cố production
├── ONBOARD_NEW_TENANT.md               # Quy trình onboard tenant mới
├── INDUSTRY_PACK_GUIDE.md              # Hướng dẫn tạo/quản lý pack
├── HOW_TO_BUILD_TOOL_PLUGIN.md          # Hướng dẫn tạo tool plugin mới
├── docker/
│   └── docker-compose.yml
├── start_dev.ps1                        # Script chạy toàn bộ môi trường dev
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
uv sync
```

### 2. Tạo file `.env`

```bash
cp .env.example .env
```

Điền các giá trị vào `.env` (xem phần [Cấu hình `.env`](#cấu-hình-env)).

### 3. Start Docker containers

> **Lưu ý:** file `.env` nằm ở thư mục gốc, còn `docker-compose.yml` nằm trong `docker/`. Phải dùng cờ `--env-file`:

```bash
docker compose -f docker/docker-compose.yml --env-file .env up -d
```

### 4. Tạo user ai_app (nếu reset volume)

```bash
docker exec -it docker-postgres-1 psql -U ai_admin -d ai_db -c "
  CREATE USER ai_app WITH PASSWORD 'your-password';
  GRANT CONNECT ON DATABASE ai_db TO ai_app;
"
```

### 5. Chạy migration

```bash
uv run alembic upgrade head
```

### 6. Seed data

```bash
uv run python scripts/seed_pricing.py
uv run python scripts/seed_test_data.py
uv run python scripts/seed_packs.py
uv run python scripts/seed_tool_definitions.py
```

### 7. Start app

```bash
uv run uvicorn src.main:app --reload
```

Mở `http://localhost:8000/docs` để xem Swagger UI.

---

## Chạy dev hàng ngày

```powershell
.\start_dev.ps1
```

Script tự động: start Docker → chờ Postgres healthy → chạy migration → start app.

---

## Cấu hình `.env`

```env
# App
APP_ENV=development

# Database
DATABASE_URL=postgresql+asyncpg://ai_app:your-password@127.0.0.1/ai_db
DATABASE_ADMIN_URL=postgresql://ai_admin:your-password@127.0.0.1/ai_db
POSTGRES_USER=ai_admin
POSTGRES_PASSWORD=your-password
POSTGRES_DB=ai_db

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

# Langfuse (observability)
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

---

## API Overview

### Authentication

Mọi request (trừ `/health`, `/ready`, `/docs`, `/openapi.json`, `/redoc`, `/metrics`) phải có headers:

| Header           | Mô tả                                                     |
|------------------|-----------------------------------------------------------|
| `X-Company-GUID` | UUID của tenant                                           |
| `X-User-GUID`    | UUID của user                                             |
| `X-Domain`       | Domain của tenant (phải có trong allowed_domains)         |
| `X-Timestamp`    | Unix timestamp (window 5 phút)                            |
| `X-Signature`    | HMAC-SHA256(secret, timestamp + body)                     |
| `X-Request-Id`   | UUID để trace (optional)                                  |

### Endpoints

| Method   | Path                                          | Mô tả                                            |
|----------|-----------------------------------------------|--------------------------------------------------|
| `GET`    | `/health`                                     | Liveness check                                   |
| `GET`    | `/ready`                                      | Readiness check                                  |
| `GET`    | `/metrics`                                    | Prometheus metrics                               |
| `GET`    | `/providers`                                  | Danh sách LLM provider đang active               |
| `POST`   | `/chat`                                       | Chat non-streaming                               |
| `POST`   | `/chat/stream`                                | Chat SSE streaming                               |
| `GET`    | `/admin/packs`                                | Danh sách industry packs                         |
| `POST`   | `/admin/packs`                                | Tạo pack mới                                     |
| `DELETE` | `/admin/packs/{pack_id}`                      | Disable pack                                     |
| `POST`   | `/admin/tenants/assign-pack`                  | Gán pack cho tenant                              |
| `POST`   | `/admin/packs/templates`                      | Tạo/cập nhật prompt template                     |
| `GET`    | `/admin/packs/{pack_id}/templates`            | Xem templates của pack                           |
| `GET`    | `/admin/tools`                                | Danh sách tất cả tool plugin                     |
| `GET`    | `/admin/tenants/{company_guid}/tools`         | Xem config tool của 1 tenant                     |
| `PUT`    | `/admin/tenants/{company_guid}/tools/{name}`  | Bật/tắt + set config tool cho tenant             |
| `DELETE` | `/admin/tenants/{company_guid}/tools/{name}`  | Xóa config tool của tenant (về default)          |
| `GET`    | `/admin/tenants/{company_guid}/tools/mcp-spec`| Export MCP-compatible tool spec cho tenant       |
| `GET`    | `/admin/tenants/{company_guid}/wallet`        | Xem ví của tenant                                |
| `POST`   | `/admin/tenants/{company_guid}/wallet/topup`  | Nạp credit                                       |
| `POST`   | `/admin/tenants/{company_guid}/wallet/grant`  | Cấp monthly grant thủ công                       |
| `GET`    | `/admin/tenants/{company_guid}/usage`         | Usage + cost 30 ngày                             |
| `GET`    | `/admin/usage/anomalies`                      | Tenant tăng đột biến > 3x baseline               |
| `GET`    | `/tenant/wallet`                              | Tenant tự xem ví                                 |
| `GET`    | `/tenant/usage`                               | Tenant tự xem usage 30 ngày                      |
| `GET`    | `/tenant/transactions`                        | Tenant tự xem lịch sử giao dịch credit           |

### POST /chat/stream (SSE)

Request:
```json
{
  "message": "tôi muốn đặt phòng Đà Nẵng",
  "conversation_id": "conv-uuid-optional",
  "intent_hint": "api_action",
  "current_screen": "hotel_search",
  "business_rules": "không nhận đặt phòng trước 24h"
}
```

Response stream — mỗi event là 1 dòng `data: {...}`:

```
data: {"type": "intent", "intent": "api_action", "confidence": 0.95}
data: {"type": "delta", "delta": "Bạn"}
data: {"type": "delta", "delta": " muốn đặt phòng"}
data: {"type": "done", "latency_ms": 823, "pack_id": "tourism@1.0.0", "usage": {...}}
```

---

## Tool Plugin System

Xem **[HOW_TO_BUILD_TOOL_PLUGIN.md](./HOW_TO_BUILD_TOOL_PLUGIN.md)** và **[INDUSTRY_PACK_GUIDE.md](./INDUSTRY_PACK_GUIDE.md)** cho chi tiết.

| Plugin | Mô tả | Config cần thiết |
|--------|-------|-----------------|
| `http_api_call` | Gọi HTTP API external | `base_url`, `headers`, `timeout` |
| `search_knowledge` | Vector search Qdrant KB | `collection` (optional, auto-fallback) |
| `web_search` | Web search qua Tavily | `api_key`, `max_results` |

---

## Credit Wallet System

Thay thế quota cứng bằng ví credit linh hoạt. 1 credit ≈ $0.01 chi phí, nhân hệ số markup configurable (default 1.5x).

### Kiến trúc

- **tenant_wallets**: 1 row per tenant — balance, monthly_grant, markup_rate, is_hard_stop
- **credit_transactions**: hypertable — lịch sử mọi giao dịch (debit, topup, monthly_grant, refund)
- **credit_packages**: danh mục gói nạp tiền

### Atomic debit chống race condition

```python
SELECT balance FROM tenant_wallets WHERE company_guid = $1 FOR UPDATE
# → khóa dòng, request khác phải đợi
UPDATE tenant_wallets SET balance = balance - charged
INSERT INTO credit_transactions (...)
```

### Background jobs (APScheduler)

- **monthly_grant_job**: mùng 1 hàng tháng lúc 00:00 — cấp credit cho tenant có monthly_grant > 0
- **reconcile_job**: mỗi giờ — đối soát credit_transactions vs llm_usage_log, cảnh báo nếu lệch

---

## Observability

### Prometheus Metrics

Endpoint `/metrics` xuất số liệu: request count, latency histogram, request/response size.

```python
Instrumentator().instrument(app).expose(app, endpoint="/metrics")
```

### Langfuse Tracing

Mọi LLM call được trace lên Langfuse Cloud: prompt, output, token count, latency, model, cost.

- **OpenAI/Groq/DeepSeek**: dùng `langfuse.openai.AsyncOpenAI` wrapper (auto-trace)
- **Gemini/Anthropic**: dùng `start_observation(as_type="generation", ...)` manual

---

## Test

### Chạy tests

```bash
uv run pytest tests/ -v          # tất cả (55 tests)
uv run pytest tests/unit/ -v     # unit tests
uv run pytest tests/security/ -v # security tests
```

### Test coverage

| Loại | Số test | Kiểm tra |
|------|---------|----------|
| Unit | 39 | Providers, classifier, memory, HMAC, pricing, model selector, wallet |
| Integration | 4 | RLS isolation, domain whitelist |
| Security | 6 | Cross-tenant wallet/transactions, HMAC replay, body tampering, SSRF |

---

## Kiến trúc bảo mật

```
Layer 1 (Network)  : HTTPS only
Layer 2 (App)      : HMAC-SHA256, anti-replay timestamp (5 phút), domain whitelist
Layer 3 (Database) : Row-Level Security — ai_app không bypass được RLS
Layer 4 (LLM)      : tenant_id inject từ middleware, không từ LLM output
Layer 5 (Tool)     : tool config per-tenant, tenant A không đọc config của tenant B
Layer 6 (Audit)    : log mọi security event vào audit_log
```

---

## Roadmap

| Sprint                                    | Tuần  | Status         |
|-------------------------------------------|-------|----------------|
| Sprint 1 — Foundation                     | 1-2   | ✅ Done        |
| Sprint 2 — Security & LLM Adapter        | 3-4   | ✅ Done        |
| Sprint 3 — Tech Debt + 5 Providers       | 5-6   | ✅ Done        |
| Sprint 4 — Agent Runtime + SSE           | 7-8   | ✅ Done        |
| Sprint 5 — Industry Pack + Template Engine| 9-10  | ✅ Done        |
| Sprint 6 — Tool Plugin + KB Multi-tenant | 11-12 | ✅ Done        |
| Sprint 7 — Credit Wallet + Admin         | 13-14 | ✅ Done        |
| Sprint 8 — Observability + Prod          | 15-16 | ✅ Done        |

---

## Troubleshooting

### Postgres role/password errors

Volume cũ bị stale. Reset:
```bash
docker compose -f docker/docker-compose.yml --env-file .env down
docker volume rm docker_postgres_data
docker compose -f docker/docker-compose.yml --env-file .env up -d
```
Sau đó tạo lại user ai_app, chạy migration, seed data.

### Extra inputs are not permitted (pydantic)

`.env` có biến mà `Settings` chưa khai báo. Thêm biến vào `src/core/config.py`.

### permission denied for table

`ai_app` chưa được GRANT. Sửa tạm:
```bash
docker exec -it docker-postgres-1 psql -U ai_admin -d ai_db -c "GRANT SELECT ON ai_service.<table> TO ai_app;"
```
Sửa gốc: thêm GRANT vào file migration.

### HMAC Invalid Signature

- Timestamp phải trong vòng 5 phút — gen lại
- Body phải giống hệt lúc gen — dùng `@scripts/test_body.json`
- GET request trên Windows cần `-d "{}"`

### Domain not allowed

Tenant chưa có domain trong `allowed_domains`. Thêm vào DB.

### Langfuse: client initialized without public_key

Restart app (lru_cache giữ settings cũ).

### Provider 503 / rate limit

Đổi provider trong `src/llm/selector.py` → restart app.

### Pack load sai / fallback generic

```bash
# Kiểm tra tenant có pack chưa
docker exec -it docker-postgres-1 psql -U ai_admin -d ai_db -c "
  SELECT * FROM ai_service.tenant_pack_assignments WHERE company_guid = '<guid>';
"
# Xóa cache pack
docker exec -it docker-redis-1 redis-cli DEL "pack:tourism@1.0.0"
```

### Data mất sau reset volume

```bash
uv run python scripts/seed_pricing.py
uv run python scripts/seed_test_data.py
uv run python scripts/seed_packs.py
uv run python scripts/seed_tool_definitions.py
```