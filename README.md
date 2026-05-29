# BE AI Assistant Service

Backend microservice độc lập xử lý toàn bộ logic AI agent — từ intent classification, multi-turn conversation, tool calling đến SSE streaming response.

**Multi-LLM Provider · Multi-Tenant · Industry Pack · Tool Plugin Architecture · Streaming SSE · Production-Ready**

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

Tính năng hiện tại (Sprint 1-6):

- **Multi-LLM provider**: Gemini, OpenAI, Anthropic, DeepSeek, Groq — swap bằng 1 dòng config, không sửa code
- **Multi-tenant với RLS**: database-level isolation, fail-closed by default
- **Industry Pack System**: mỗi vertical là 1 pack versioned (tourism, generic, spa_booking...) — onboard khách mới chỉ cần assign pack, không cần code
- **Prompt Template Engine**: Jinja2 templates lưu DB, versioned, render runtime với context inject — đổi prompt không redeploy
- **SSE streaming**: response stream từng token về FE, time-to-first-token < 1.5s
- **Intent classifier**: tự động phân loại intent theo pack config (general_chat, search_knowledge, api_action, summarize...)
- **Multi-turn memory**: Redis sliding window 10 turn, TTL 24h per conversation
- **Tool Plugin Architecture**: dynamic plugin loading từ filesystem, config per-tenant từ DB, MCP-compatible spec export
- **KB Multi-tenant**: Qdrant collection routing theo tenant (`{company_guid}_docs`), không chia sẻ KB giữa các tenant
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
| Vector DB       | Qdrant                            |
| Template Engine | Jinja2                            |
| Migration       | Alembic                           |
| Package manager | uv                                |
| Container       | Docker + Docker Compose           |
| LLM Tracing     | Langfuse (self-hosted, Sprint 8)  |

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
│   │   ├── admin_packs.py               # Admin: CRUD pack, assign tenant, upsert template
│   │   └── admin_tools.py               # Admin: CRUD tool config per-tenant, MCP spec export
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
│   │       ├── gemini.py
│   │       ├── openai_provider.py
│   │       ├── anthropic_provider.py
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
│   │   ├── tool_config.py               # Load + configure tools per-tenant từ DB
│   │   └── qdrant_search.py             # Vector search
│   └── tools/
│       ├── base.py                      # BaseTool, ToolRegistry, configure(), to_mcp_spec()
│       ├── loader.py                    # ToolPluginLoader — dynamic discover + register
│       └── plugins/                     # Tool plugins — thêm plugin mới vào đây
│           ├── __init__.py
│           ├── http_api_call.py         # Gọi external HTTP API per-tenant
│           ├── search_knowledge.py      # Qdrant vector search, collection per-tenant
│           └── web_search.py            # Web search qua Tavily API
├── tests/
│   ├── integration/
│   │   └── test_rls.py                  # RLS isolation test
│   └── unit/
│       ├── test_packs.py
│       ├── test_classifier.py
│       ├── test_memory.py
│       ├── test_tools.py
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
│       └── d365ee120fbf_006_sprint6_tool_plugin.py
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
├── HOW_TO_BUILD_TOOL_PLUGIN.md          # Hướng dẫn tạo tool plugin mới
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

### 5. Seed data

```bash
uv run python scripts/seed_pricing.py
uv run python scripts/seed_test_data.py
uv run python scripts/seed_packs.py
uv run python scripts/seed_tool_definitions.py   # Sprint 6 — seed tool plugins
```

### 6. Assign pack cho tenant test

```bash
# Vào psql
docker exec -it docker-postgres-1 psql -U postgres -d ai_db

# Assign pack
INSERT INTO ai_service.tenant_pack_assignments (company_guid, pack_id, overrides)
VALUES ('<company-guid>', 'tourism@1.0.0', '{}')
ON CONFLICT (company_guid) DO UPDATE SET pack_id = 'tourism@1.0.0';
```

### 7. (Optional) Enable tool cho tenant

```bash
# Set config http_api_call cho tenant
curl -X PUT http://localhost:8000/admin/tenants/<company_guid>/tools/http_api_call \
  -H "Content-Type: application/json" \
  -H "X-Company-GUID: <company_guid>" \
  -H "X-User-GUID: <user_guid>" \
  -H "X-Domain: <domain>" \
  -H "X-Timestamp: <timestamp>" \
  -H "X-Signature: <signature>" \
  -d '{"is_enabled": true, "config": {"base_url": "https://your-api.com", "timeout": 15}}'
```

### 8. Start app

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

| Header           | Mô tả                                                     |
|------------------|-----------------------------------------------------------|
| `X-Company-GUID` | UUID của tenant                                           |
| `X-User-GUID`    | UUID của user                                             |
| `X-Domain`       | Domain của tenant (phải có trong allowed_domains)         |
| `X-Timestamp`    | Unix timestamp (window 5 phút)                            |
| `X-Signature`    | HMAC-SHA256(secret, timestamp + body)                     |
| `X-Request-Id`   | UUID để trace (optional)                                  |

Generate signature để test:

```bash
# Sửa scripts/test_body.json với body muốn test
uv run python scripts/gen_hmac.py
```

> **Lưu ý khi test bằng curl.exe trên Windows:** mọi request dù là GET cũng cần truyền `-d "{}"` để HMAC tính đúng body.

### Endpoints

| Method   | Path                                          | Mô tả                                            |
|----------|-----------------------------------------------|--------------------------------------------------|
| `GET`    | `/health`                                     | Liveness check                                   |
| `GET`    | `/ready`                                      | Readiness check                                  |
| `GET`    | `/providers`                                  | Danh sách LLM provider đang active               |
| `POST`   | `/chat`                                       | Chat non-streaming                               |
| `POST`   | `/chat/stream`                                | Chat SSE streaming                               |
| `GET`    | `/admin/packs`                                | Danh sách industry packs                         |
| `POST`   | `/admin/packs`                                | Tạo pack mới                                     |
| `DELETE` | `/admin/packs/{pack_id}`                      | Disable pack                                     |
| `POST`   | `/admin/tenants/assign-pack`                  | Gán pack cho tenant                              |
| `POST`   | `/admin/packs/templates`                      | Tạo/cập nhật prompt template                     |
| `GET`    | `/admin/packs/{pack_id}/templates`            | Xem templates của pack                           |
| `GET`    | `/admin/tools`                                | Danh sách tất cả tool plugin trong hệ thống      |
| `GET`    | `/admin/tenants/{company_guid}/tools`         | Xem config tool của 1 tenant                     |
| `PUT`    | `/admin/tenants/{company_guid}/tools/{name}`  | Bật/tắt + set config tool cho tenant             |
| `DELETE` | `/admin/tenants/{company_guid}/tools/{name}`  | Xóa config tool của tenant (về default)          |
| `GET`    | `/admin/tenants/{company_guid}/tools/mcp-spec`| Export MCP-compatible tool spec cho tenant       |

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

| Type     | Mô tả                                    |
|----------|------------------------------------------|
| `intent` | Intent đã classify được                  |
| `delta`  | Token mới từ LLM                         |
| `done`   | Kết thúc, kèm latency + usage + pack_id  |
| `error`  | Lỗi trong quá trình xử lý               |

---

## Tool Plugin System

Sprint 6 giới thiệu **Tool Plugin Architecture** — tools không còn hardcode mà là plugin class có thể config per-tenant.

### Kiến trúc

```
App startup
    └── ToolPluginLoader.discover()
            └── scan src/tools/plugins/
                    └── auto-register mọi subclass của BaseTool

Request đến
    └── Orchestrator
            └── ToolConfigService.get_tools_for_tenant()
                    └── query tenant_tool_configs từ DB
                            └── tool.configure(config) → instance per-tenant
```

### Nguyên tắc quan trọng

- **Code plugin nằm trên filesystem** — DB chỉ chứa metadata + config, KHÔNG lưu Python code vào DB
- **Cùng plugin, khác config** — tenant du lịch và F&B dùng chung `http_api_call` nhưng trỏ về 2 API khác nhau
- **Tenant isolation** — tenant A enable tool X, tenant B không enable → agent B không thấy tool X
- **KB isolation** — `search_knowledge` tự động route về Qdrant collection `{company_guid}_docs`

### Tool plugins có sẵn

| Plugin | Mô tả | Config cần thiết |
|--------|-------|-----------------|
| `http_api_call` | Gọi HTTP API external | `base_url`, `headers`, `timeout` |
| `search_knowledge` | Vector search Qdrant KB | `collection` (optional, auto-fallback) |
| `web_search` | Web search qua Tavily | `api_key`, `max_results` |

### Enable tool cho tenant

```bash
# Bật http_api_call cho tenant F&B
curl -X PUT /admin/tenants/<guid>/tools/http_api_call \
  -d '{"is_enabled": true, "config": {"base_url": "https://pos.fnb.vn", "timeout": 15}}'

# Xem MCP spec — danh sách tool enabled cho tenant
curl /admin/tenants/<guid>/tools/mcp-spec
```

### Tạo tool plugin mới

Xem hướng dẫn chi tiết tại **[HOW_TO_BUILD_TOOL_PLUGIN.md](./HOW_TO_BUILD_TOOL_PLUGIN.md)**.

Tóm tắt 6 bước:
1. Tạo file `src/tools/plugins/ten_tool.py`, kế thừa `BaseTool`
2. Implement `configure()`, `_run()`
3. Seed vào `tool_definitions` qua `scripts/seed_tool_definitions.py`
4. Thêm vào `tool_whitelist` của pack
5. Config cho tenant qua PUT endpoint
6. Restart app — `ToolPluginLoader` tự discover

---

## Industry Pack System

Pack là đơn vị config cho 1 vertical, immutable theo version.

```
Pack tourism@1.0.0
├── intents: [general_chat, search_knowledge, api_action, summarize]
├── tool_whitelist: [search_knowledge, http_api_call]
├── default_models: {classifier: groq/llama, executor: deepseek/deepseek-chat}
└── prompt_templates:
    ├── general_chat:system → "Bạn là trợ lý của {{ tenant_name }}..."
    └── api_action:system   → "Bạn hỗ trợ đặt phòng cho {{ tenant_name }}..."
```

**Onboard khách mới = assign pack + (optional) override + enable tools** — không cần deploy lại.

**Tenant override:**

```json
{
  "prompts": {
    "general_chat:system": "Prompt riêng của tenant này..."
  },
  "default_models": {
    "executor": {"provider": "anthropic", "model": "claude-haiku-4-5"}
  },
  "extra_tools": ["web_search"]
}
```

---

## Multi-Provider Config

Đổi provider mặc định trong `src/llm/selector.py`:

```python
DEFAULT_MODELS = {
    "classifier": ("groq", "llama-3.1-8b-instant"),   # nhanh, rẻ
    "executor":   ("deepseek", "deepseek-chat"),       # balance
    "summarizer": ("deepseek", "deepseek-chat"),       # rẻ
    "premium":    ("anthropic", "claude-haiku-4-5"),   # quality cao
}
```

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

### Test API thủ công

```bash
# Bước 1: Sửa body test
echo '{"message": "xin chao"}' > scripts/test_body.json

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
  -d "@scripts/test_body.json"
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
Layer 5 (Tool)     : tool config per-tenant, tenant A không đọc config của tenant B
Layer 6 (Audit)    : log mọi security event vào audit_log
```

### HMAC verification

```
signature = HMAC-SHA256(HMAC_SECRET, f"{timestamp}{request_body}")
```

- `HMAC_SECRET` — khóa cố định, lưu trong `.env`, chia sẻ out-of-band với client
- Client tự gen `timestamp` + `signature` mỗi request — server verify lại
- Timestamp window 5 phút — chống replay attack
- `hmac.compare_digest` — chống timing attack
- Pure ASGI middleware — compatible với SSE streaming

### Multi-tenant isolation

- RLS policy filter tự động tất cả queries theo `app.current_tenant`
- `ai_app` role không có `BYPASSRLS`
- `allowed_domains` table kiểm tra domain whitelist chống SSRF
- `tenant_tool_configs` có RLS — tenant A không đọc được config tool của tenant B
- Qdrant collection routing `{company_guid}_docs` — KB hoàn toàn isolated

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
| Sprint 7 — Credit Wallet + Admin         | 13-14 | ⏳ Pending     |
| Sprint 8 — Observability + Prod          | 15-16 | ⏳ Pending     |

---

## Troubleshooting

### HMAC Invalid Signature

- Timestamp phải trong vòng 5 phút — gen lại nếu quá hạn
- Body phải giống hệt lúc gen — dùng `@scripts/test_body.json`, không dùng inline `-d '{...}'`
- GET request trên Windows cần `-d "{}"` để HMAC tính đúng
- Chạy lại `uv run python scripts/gen_hmac.py`

### Domain not allowed

Tenant chưa có domain trong `allowed_domains`. Thêm vào DB:
```bash
uv run python fix_domain.py
```

### Tool không xuất hiện trong MCP spec

- Kiểm tra tool đã được `enable` cho tenant chưa qua `GET /admin/tenants/<guid>/tools`
- `is_enabled: null` nghĩa là chưa config — gọi PUT endpoint để enable
- Kiểm tra `tool_name` trong pack `tool_whitelist` có khớp với tên plugin không

### Tool plugin không load khi startup

Kiểm tra log startup — nếu không thấy `tool.plugin.registered`:
- Class có kế thừa `BaseTool` không?
- `name` có bị để rỗng không?
- File có nằm đúng trong `src/tools/plugins/` không?
- Import trong file có lỗi syntax không?

### search_knowledge tìm sai KB

Kiểm tra Qdrant collection có tồn tại không:
```
collection name: {company_guid}_docs
```
Nếu chưa có thì cần upload document cho tenant đó trước.

### Provider 503 / rate limit

Đổi provider trong `src/llm/selector.py` → đổi `executor` sang provider khác → restart app.

### Redis connection refused

```bash
docker compose -f docker/docker-compose.yml up -d
```

### Data mất sau restart

```bash
uv run python scripts/seed_test_data.py
uv run python scripts/seed_pricing.py
uv run python scripts/seed_packs.py
uv run python scripts/seed_tool_definitions.py
```

### Pack không load đúng

Xóa Redis cache của pack rồi thử lại:
```bash
docker exec -it docker-redis-1 redis-cli DEL "pack:tourism@1.0.0"
```

### Tenant dùng wrong pack / fallback generic

```sql
SELECT * FROM ai_service.tenant_pack_assignments WHERE company_guid = '<guid>';
```

Nếu không có row → assign pack lại qua `/admin/tenants/assign-pack`.

### `unrecognized configuration parameter app.current_tenant`

Cần chạy `SET LOCAL` trong transaction. Xem `src/db/session.py`.

### RLS error khi gọi tool config

Đảm bảo `set_config('app.current_tenant', ...)` và query nằm trong cùng 1 transaction. Xem `src/services/tool_config.py`.