# BE AI Assistant Service

A standalone backend microservice that handles all AI agent logic — from intent classification, multi-turn conversation, and tool calling, to SSE streaming responses.

**Multi-LLM Provider · Multi-Tenant · Industry Pack · Tool Plugin Architecture · Streaming SSE · Credit Wallet · Observability · Production-Ready**

---

## Table of Contents

- [Overview](#overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Environment Requirements](#environment-requirements)
- [First-Time Setup](#first-time-setup)
- [Daily Dev Workflow](#daily-dev-workflow)
- [`.env` Configuration](#env-configuration)
- [API Overview](#api-overview)
- [Tool Plugin System](#tool-plugin-system)
- [Credit Wallet System](#credit-wallet-system)
- [Observability](#observability)
- [Tests](#tests)
- [Security Architecture](#security-architecture)
- [Roadmap](#roadmap)
- [Troubleshooting](#troubleshooting)

---

## Overview

BE AI Service is a standalone microservice that **does not share a database with the main backend**. Every incoming request has already been authenticated by BE Private, which signs the request with HMAC-SHA256 before forwarding it to the AI Service.

```
FE → BE Private (auth user) → BE AI Service (HMAC verify → classify → stream response)
```

Current features (Sprint 1-8):

- **Multi-LLM provider**: Gemini, OpenAI, Anthropic, DeepSeek, Groq — swap with a single config change, no code changes
- **Multi-tenant with RLS**: database-level isolation, fail-closed by default
- **Industry Pack System**: each vertical is a versioned pack (tourism, generic, spa_booking...) — onboarding a new client only requires assigning a pack, no code needed
- **Prompt Template Engine**: Jinja2 templates stored in DB, versioned, rendered at runtime with context injection — change prompts without redeploying
- **SSE streaming**: response streamed token-by-token to the FE, time-to-first-token < 1.5s
- **Intent classifier**: automatically classifies intent based on pack config (general_chat, search_knowledge, api_action, summarize...)
- **Multi-turn memory**: Redis sliding window of 10 turns, 24h TTL per conversation
- **Tool Plugin Architecture**: dynamic plugin loading from the filesystem, per-tenant config from DB, MCP-compatible spec export
- **KB Multi-tenant**: Qdrant collection routing per tenant (`{company_guid}_docs`), no KB sharing between tenants
- **Credit Wallet**: a credit wallet replacing hard quotas, atomic debit to prevent race conditions (FOR UPDATE), configurable markup, monthly grant + reconcile job
- **Observability**: Prometheus metrics at `/metrics`, Langfuse tracing for every LLM call (prompt, tokens, latency, cost)
- **Usage tracking**: logs every LLM call with estimated cost per tenant
- **Domain whitelist**: prevents SSRF, checks allowed_domains per tenant

---

## Tech Stack

| Component       | Technology                                     |
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

## Project Structure

```
ai-assistant-service/
├── src/
│   ├── main.py                          # FastAPI app entry, lifespan, middleware
│   ├── agents/
│   │   ├── base.py                      # BaseAgent, run(), stream()
│   │   ├── classifier.py                # ClassifierAgent — intent classification
│   │   ├── orchestrator.py              # Orchestrator — load pack → classify → load tools → stream
│   │   └── registry.py                  # AgentRegistry — maps intent → executor
│   ├── api/
│   │   ├── chat.py                      # POST /chat, POST /chat/stream (SSE)
│   │   ├── providers.py                 # GET /providers
│   │   ├── admin_packs.py              # Admin: CRUD pack, assign tenant, upsert template
│   │   ├── admin_tools.py              # Admin: CRUD tool config per tenant, MCP spec export
│   │   ├── admin_wallet.py             # Admin: wallet topup, grant, usage, anomalies
│   │   └── tenant_wallet.py            # Tenant: self-serve wallet, usage, transactions
│   ├── cache/
│   │   └── redis_client.py              # Redis connection + get_redis()
│   ├── core/
│   │   └── config.py                    # Settings loaded from .env (pydantic-settings)
│   ├── db/
│   │   └── session.py                   # asyncpg pool + RLS tenant context
│   ├── llm/
│   │   ├── base.py                      # LLMProvider abstract, dataclasses
│   │   ├── registry.py                  # Provider registry
│   │   ├── selector.py                  # ModelSelector — role-based provider selection
│   │   ├── pricing.py                   # Cost calculator
│   │   └── providers/
│   │       ├── gemini.py                # + Langfuse tracing
│   │       ├── openai_provider.py       # + Langfuse wrapper (also covers Groq/DeepSeek)
│   │       ├── anthropic_provider.py    # + Langfuse tracing
│   │       ├── deepseek_provider.py
│   │       └── groq_provider.py
│   ├── memory/
│   │   └── conversation.py              # Redis sliding window memory
│   ├── middleware/
│   │   └── tenant.py                    # Pure ASGI HMACMiddleware
│   ├── packs/
│   │   ├── loader.py                    # Loads pack from DB, cached in Redis for 5 minutes
│   │   ├── resolver.py                  # Merges pack default + tenant override → EffectiveConfig
│   │   └── template_engine.py           # Jinja2 prompt rendering with context injection
│   ├── services/
│   │   ├── audit.py                     # Security event logger
│   │   ├── usage_logger.py              # Async LLM usage logger
│   │   ├── tool_config.py              # Loads + configures tools per tenant from DB
│   │   ├── wallet.py                   # WalletService: check_balance, debit, credit, grant_monthly
│   │   ├── wallet_gate.py             # WalletGate: check before / debit after every LLM call
│   │   ├── scheduler.py               # APScheduler: monthly_grant_job + reconcile_job
│   │   └── qdrant_search.py            # Vector search
│   └── tools/
│       ├── base.py                      # BaseTool, ToolRegistry, configure(), to_mcp_spec()
│       ├── loader.py                    # ToolPluginLoader — dynamic discovery + registration
│       └── plugins/
│           ├── __init__.py
│           ├── http_api_call.py         # Calls an external HTTP API per tenant
│           ├── search_knowledge.py      # Qdrant vector search, collection per tenant
│           └── web_search.py            # Web search via the Tavily API
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
│   ├── gen_hmac.py                      # Generate an HMAC signature for testing
│   ├── seed_pricing.py                  # Seed LLM pricing (5 providers)
│   ├── seed_test_data.py                # Seed a test tenant
│   ├── seed_packs.py                    # Seed 3 industry packs + prompt templates
│   ├── seed_tool_definitions.py         # Seed tool definitions into the DB
│   ├── check_tables.py                  # Inspect DB tables
│   ├── check_domains.py                 # Inspect allowed_domains
│   ├── check_usage.py                   # View cost + usage from the DB
│   └── test_body.json                   # Sample body for testing the API
├── INCIDENT_RUNBOOK.md                  # Production incident handling
├── ONBOARD_NEW_TENANT.md               # New tenant onboarding process
├── INDUSTRY_PACK_GUIDE.md              # Guide to creating/managing packs
├── HOW_TO_BUILD_TOOL_PLUGIN.md          # Guide to building a new tool plugin
├── docker/
│   └── docker-compose.yml
├── start_dev.ps1                        # Script that runs the entire dev environment
├── conftest.py
├── pyproject.toml
└── README.md
```

---

## Environment Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) — package manager
- Docker Desktop
- At least 1 LLM API key (the Gemini free tier is enough for development)

---

## First-Time Setup

### 1. Clone and set up the environment

```bash
git clone <repo-url>
cd ai-assistant-service
uv sync
```

### 2. Create the `.env` file

```bash
cp .env.example .env
```

Fill in the values in `.env` (see [`.env` Configuration](#env-configuration)).

### 3. Start Docker containers

> **Note:** the `.env` file lives at the project root, while `docker-compose.yml` lives in `docker/`. You must use the `--env-file` flag:

```bash
docker compose -f docker/docker-compose.yml --env-file .env up -d
```

### 4. Create the `ai_app` user (if you reset the volume)

```bash
docker exec -it docker-postgres-1 psql -U ai_admin -d ai_db -c "
  CREATE USER ai_app WITH PASSWORD 'your-password';
  GRANT CONNECT ON DATABASE ai_db TO ai_app;
"
```

### 5. Run migrations

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

### 7. Start the app

```bash
uv run uvicorn src.main:app --reload
```

Open `http://localhost:8000/docs` to view the Swagger UI.

---

## Daily Dev Workflow

```powershell
.\start_dev.ps1
```

The script automatically: starts Docker → waits for Postgres to be healthy → runs migrations → starts the app.

---

## `.env` Configuration

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

# LLM Providers — fill in at least 1
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

Every request (except `/health`, `/ready`, `/docs`, `/openapi.json`, `/redoc`, `/metrics`) must include the following headers:

| Header           | Description                                               |
|------------------|-----------------------------------------------------------|
| `X-Company-GUID` | Tenant UUID                                               |
| `X-User-GUID`    | User UUID                                                 |
| `X-Domain`       | Tenant domain (must be in allowed_domains)                |
| `X-Timestamp`    | Unix timestamp (5-minute window)                          |
| `X-Signature`    | HMAC-SHA256(secret, timestamp + body)                     |
| `X-Request-Id`   | UUID for tracing (optional)                               |

### Endpoints

| Method   | Path                                          | Description                                      |
|----------|-----------------------------------------------|--------------------------------------------------|
| `GET`    | `/health`                                     | Liveness check                                   |
| `GET`    | `/ready`                                      | Readiness check                                  |
| `GET`    | `/metrics`                                    | Prometheus metrics                               |
| `GET`    | `/providers`                                  | List of currently active LLM providers          |
| `POST`   | `/chat`                                       | Non-streaming chat                               |
| `POST`   | `/chat/stream`                                | SSE streaming chat                               |
| `GET`    | `/admin/packs`                                | List industry packs                              |
| `POST`   | `/admin/packs`                                | Create a new pack                                |
| `DELETE` | `/admin/packs/{pack_id}`                      | Disable a pack                                   |
| `POST`   | `/admin/tenants/assign-pack`                  | Assign a pack to a tenant                        |
| `POST`   | `/admin/packs/templates`                      | Create/update a prompt template                  |
| `GET`    | `/admin/packs/{pack_id}/templates`            | View templates for a pack                        |
| `GET`    | `/admin/tools`                                | List all tool plugins                            |
| `GET`    | `/admin/tenants/{company_guid}/tools`         | View a tenant's tool config                      |
| `PUT`    | `/admin/tenants/{company_guid}/tools/{name}`  | Enable/disable + set tool config for a tenant    |
| `DELETE` | `/admin/tenants/{company_guid}/tools/{name}`  | Remove a tenant's tool config (revert to default)|
| `GET`    | `/admin/tenants/{company_guid}/tools/mcp-spec`| Export the MCP-compatible tool spec for a tenant |
| `GET`    | `/admin/tenants/{company_guid}/wallet`        | View a tenant's wallet                           |
| `POST`   | `/admin/tenants/{company_guid}/wallet/topup`  | Top up credits                                   |
| `POST`   | `/admin/tenants/{company_guid}/wallet/grant`  | Manually issue the monthly grant                 |
| `GET`    | `/admin/tenants/{company_guid}/usage`         | Usage + cost over the last 30 days               |
| `GET`    | `/admin/usage/anomalies`                      | Tenants with usage spikes > 3x baseline          |
| `GET`    | `/tenant/wallet`                              | Tenant self-service: view wallet                 |
| `GET`    | `/tenant/usage`                               | Tenant self-service: view 30-day usage           |
| `GET`    | `/tenant/transactions`                        | Tenant self-service: view credit transaction history |

### POST /chat/stream (SSE)

Request:
```json
{
  "message": "I'd like to book a room in Da Nang",
  "conversation_id": "conv-uuid-optional",
  "intent_hint": "api_action",
  "current_screen": "hotel_search",
  "business_rules": "no bookings accepted less than 24h in advance"
}
```

Response stream — each event is one `data: {...}` line:

```
data: {"type": "intent", "intent": "api_action", "confidence": 0.95}
data: {"type": "delta", "delta": "Sure"}
data: {"type": "delta", "delta": ", I can help you book a room"}
data: {"type": "done", "latency_ms": 823, "pack_id": "tourism@1.0.0", "usage": {...}}
```

---

## Tool Plugin System

See **[HOW_TO_BUILD_TOOL_PLUGIN.md](./HOW_TO_BUILD_TOOL_PLUGIN.md)** and **[INDUSTRY_PACK_GUIDE.md](./INDUSTRY_PACK_GUIDE.md)** for details.

| Plugin | Description | Required Config |
|--------|-------|-----------------|
| `http_api_call` | Calls an external HTTP API | `base_url`, `headers`, `timeout` |
| `search_knowledge` | Vector search over the Qdrant KB | `collection` (optional, auto-fallback) |
| `web_search` | Web search via Tavily | `api_key`, `max_results` |

---

## Credit Wallet System

Replaces hard quotas with a flexible credit wallet. 1 credit ≈ $0.01 of cost, multiplied by a configurable markup factor (default 1.5x).

### Architecture

- **tenant_wallets**: 1 row per tenant — balance, monthly_grant, markup_rate, is_hard_stop
- **credit_transactions**: hypertable — history of every transaction (debit, topup, monthly_grant, refund)
- **credit_packages**: catalog of top-up packages

### Atomic debit to prevent race conditions

```python
SELECT balance FROM tenant_wallets WHERE company_guid = $1 FOR UPDATE
# → locks the row, other requests must wait
UPDATE tenant_wallets SET balance = balance - charged
INSERT INTO credit_transactions (...)
```

### Background jobs (APScheduler)

- **monthly_grant_job**: runs at 00:00 on the 1st of each month — issues credits to tenants with monthly_grant > 0
- **reconcile_job**: runs hourly — reconciles credit_transactions against llm_usage_log, raises an alert if there's a mismatch

---

## Observability

### Prometheus Metrics

The `/metrics` endpoint exposes metrics: request count, latency histogram, request/response size.

```python
Instrumentator().instrument(app).expose(app, endpoint="/metrics")
```

### Langfuse Tracing

Every LLM call is traced to Langfuse Cloud: prompt, output, token count, latency, model, cost.

- **OpenAI/Groq/DeepSeek**: uses the `langfuse.openai.AsyncOpenAI` wrapper (auto-trace)
- **Gemini/Anthropic**: uses `start_observation(as_type="generation", ...)` manually

---

## Tests

### Running tests

```bash
uv run pytest tests/ -v          # all tests (55 tests)
uv run pytest tests/unit/ -v     # unit tests
uv run pytest tests/security/ -v # security tests
```

### Test coverage

| Type | Test count | Covers |
|------|---------|----------|
| Unit | 39 | Providers, classifier, memory, HMAC, pricing, model selector, wallet |
| Integration | 4 | RLS isolation, domain whitelist |
| Security | 6 | Cross-tenant wallet/transactions, HMAC replay, body tampering, SSRF |

---

## Security Architecture

```
Layer 1 (Network)  : HTTPS only
Layer 2 (App)      : HMAC-SHA256, anti-replay timestamp (5 minutes), domain whitelist
Layer 3 (Database) : Row-Level Security — ai_app cannot bypass RLS
Layer 4 (LLM)      : tenant_id injected from middleware, never from LLM output
Layer 5 (Tool)     : per-tenant tool config — tenant A cannot read tenant B's config
Layer 6 (Audit)    : every security event is logged to audit_log
```

---

## Roadmap

| Sprint                                    | Week  | Status         |
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

The old volume is stale. Reset it:
```bash
docker compose -f docker/docker-compose.yml --env-file .env down
docker volume rm docker_postgres_data
docker compose -f docker/docker-compose.yml --env-file .env up -d
```
Then recreate the `ai_app` user, run migrations, and seed data.

### Extra inputs are not permitted (pydantic)

`.env` contains a variable that `Settings` doesn't declare. Add the variable to `src/core/config.py`.

### permission denied for table

`ai_app` hasn't been granted access. Quick fix:
```bash
docker exec -it docker-postgres-1 psql -U ai_admin -d ai_db -c "GRANT SELECT ON ai_service.<table> TO ai_app;"
```
Proper fix: add the GRANT to a migration file.

### HMAC Invalid Signature

- The timestamp must be within 5 minutes — regenerate it
- The body must be byte-identical to the one used when signing — use `@scripts/test_body.json`
- GET requests on Windows need `-d "{}"`

### Domain not allowed

The tenant doesn't have this domain in `allowed_domains`. Add it to the DB.

### Langfuse: client initialized without public_key

Restart the app (lru_cache is holding onto stale settings).

### Provider 503 / rate limit

Change the provider in `src/llm/selector.py` → restart the app.

### Pack loads incorrectly / falls back to generic

```bash
# Check whether the tenant has a pack assigned
docker exec -it docker-postgres-1 psql -U ai_admin -d ai_db -c "
  SELECT * FROM ai_service.tenant_pack_assignments WHERE company_guid = '<guid>';
"
# Clear the pack cache
docker exec -it docker-redis-1 redis-cli DEL "pack:tourism@1.0.0"
```

### Data lost after resetting the volume

```bash
uv run python scripts/seed_pricing.py
uv run python scripts/seed_test_data.py
uv run python scripts/seed_packs.py
uv run python scripts/seed_tool_definitions.py
```
