# Incident Runbook — BE AI Assistant Service

## 1. App không start được

**Triệu chứng:** uvicorn crash ngay khi khởi động.

**Checklist:**
```bash
# Kiểm tra postgres + redis có healthy không
docker ps

# Kiểm tra .env có đủ biến không
cat .env

# Chạy migration nếu thiếu schema
uv run alembic upgrade head
```

---

## 2. password authentication failed

**Triệu chứng:** `asyncpg.exceptions.InvalidPasswordError`

**Fix:**
```bash
# Reset volume và tạo lại
docker compose -f docker/docker-compose.yml --env-file .env down
docker volume rm docker_postgres_data
docker compose -f docker/docker-compose.yml --env-file .env up -d
uv run alembic upgrade head
uv run python scripts/seed_pricing.py
uv run python scripts/seed_test_data.py
uv run python scripts/seed_packs.py
uv run python scripts/seed_tool_definitions.py
```

---

## 3. HMAC Invalid Signature

**Triệu chứng:** `401 INVALID_SIGNATURE`

**Checklist:**
- Timestamp phải trong vòng 5 phút — gen lại
- Body phải giống hệt lúc sign — dùng `@scripts/test_body.json`
- GET request trên Windows cần `-d "{}"`
- `HMAC_SECRET` trong `.env` phải khớp với client

```bash
uv run python scripts/gen_hmac.py
```

---

## 4. Domain not allowed

**Triệu chứng:** `403 DOMAIN_NOT_ALLOWED`

**Fix:**
```bash
docker exec -it docker-postgres-1 psql -U ai_admin -d ai_db -c "
INSERT INTO ai_service.allowed_domains (company_guid, domain, is_active)
VALUES ('<guid>', 'https://your-domain.com', TRUE)
ON CONFLICT DO NOTHING;
"
```

---

## 5. Provider 503 / rate limit

**Triệu chứng:** LLM call fail, log báo 503 hoặc rate limit.

**Fix:**
```python
# src/llm/selector.py — đổi executor sang provider khác
DEFAULT_MODELS = {
    "executor": ("groq", "llama-3.1-8b-instant"),  # fallback rẻ + nhanh
}
```
Restart app sau khi đổi.

---

## 6. Redis connection refused

**Triệu chứng:** `ConnectionRefusedError: [Errno 111]`

**Fix:**
```bash
docker compose -f docker/docker-compose.yml --env-file .env up -d
```

---

## 7. Tenant hết credit — bị hard stop

**Triệu chứng:** chat trả về `402` hoặc `InsufficientBalanceError` trong log.

**Fix — top-up qua API:**
```bash
curl -X POST http://localhost:8000/admin/tenants/<guid>/wallet/topup \
  -H "Content-Type: application/json" \
  -d '{"credits": 1000, "note": "manual topup"}'
```

---

## 8. Pack không load — fallback generic

**Triệu chứng:** tenant dùng sai pack hoặc intent classify sai.

**Checklist:**
```bash
# Kiểm tra tenant có được assign pack chưa
docker exec -it docker-postgres-1 psql -U ai_admin -d ai_db -c "
SELECT * FROM ai_service.tenant_pack_assignments
WHERE company_guid = '<guid>';
"

# Xóa cache Redis nếu pack đang stale
docker exec -it docker-redis-1 redis-cli DEL "pack:tourism@1.0.0"
```

---

## 9. Tool plugin không load khi startup

**Triệu chứng:** log startup không có `tool.plugin.registered`.

**Checklist:**
- Class có kế thừa `BaseTool` không?
- File có nằm trong `src/tools/plugins/` không?
- Import có lỗi syntax không?

```bash
uv run python -c "from src.tools.loader import ToolPluginLoader; ToolPluginLoader.discover()"
```

---

## 10. Data mất sau reset volume

**Triệu chứng:** migration pass nhưng không có data.

**Fix — seed lại:**
```bash
uv run python scripts/seed_pricing.py
uv run python scripts/seed_test_data.py
uv run python scripts/seed_packs.py
uv run python scripts/seed_tool_definitions.py
```

---

## 11. Anomaly alert — tenant tăng đột biến

**Triệu chứng:** `GET /admin/usage/anomalies` trả về tenant có ratio > 3.

**Checklist:**
- Xem usage chi tiết: `GET /admin/tenants/<guid>/usage`
- Kiểm tra có bị abuse không — xem `audit_log`
- Tạm thời set `is_hard_stop = TRUE` và balance về 0 nếu cần block:

```bash
docker exec -it docker-postgres-1 psql -U ai_admin -d ai_db -c "
UPDATE ai_service.tenant_wallets
SET is_hard_stop = TRUE, balance = 0
WHERE company_guid = '<guid>';
"
```

---

## 12. RLS error — cross-tenant query

**Triệu chứng:** `unrecognized configuration parameter app.current_tenant`

**Fix:** Đảm bảo mọi query đều dùng `acquire_with_tenant()`:
```python
async with DatabasePool.acquire_with_tenant(company_guid) as conn:
    # query here
```

---

## Rollback plan

| Tình huống | Thời gian | Cách rollback |
|---|---|---|
| Schema mới lỗi | < 5 phút | `uv run alembic downgrade -1` |
| App crash sau deploy | < 2 phút | `git revert` + redeploy |
| Wallet system lỗi | < 15 phút | Set `USE_LEGACY_QUOTA=true` trong `.env` |
| Traffic AI Service lỗi | < 15 phút | Route về n8n cũ qua flag BE Private |