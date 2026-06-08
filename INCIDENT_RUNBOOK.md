# Incident Runbook — BE AI Assistant Service

## 1. App fails to start

**Symptom:** uvicorn crashes immediately on startup.

**Checklist:**
```bash
# Check whether postgres + redis are healthy
docker ps

# Check that .env has all required variables
cat .env

# Run migrations if the schema is missing
uv run alembic upgrade head
```

---

## 2. password authentication failed

**Symptom:** `asyncpg.exceptions.InvalidPasswordError`

**Fix:**
```bash
# Reset the volume and recreate everything
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

**Symptom:** `401 INVALID_SIGNATURE`

**Checklist:**
- The timestamp must be within 5 minutes — regenerate it
- The body must be byte-identical to the one used for signing — use `@scripts/test_body.json`
- GET requests on Windows need `-d "{}"`
- `HMAC_SECRET` in `.env` must match the client's

```bash
uv run python scripts/gen_hmac.py
```

---

## 4. Domain not allowed

**Symptom:** `403 DOMAIN_NOT_ALLOWED`

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

**Symptom:** LLM call fails, log shows 503 or rate limit.

**Fix:**
```python
# src/llm/selector.py — switch the executor to a different provider
DEFAULT_MODELS = {
    "executor": ("groq", "llama-3.1-8b-instant"),  # cheap + fast fallback
}
```
Restart the app after making the change.

---

## 6. Redis connection refused

**Symptom:** `ConnectionRefusedError: [Errno 111]`

**Fix:**
```bash
docker compose -f docker/docker-compose.yml --env-file .env up -d
```

---

## 7. Tenant out of credit — hard stop triggered

**Symptom:** chat returns `402` or `InsufficientBalanceError` appears in the log.

**Fix — top up via the API:**
```bash
curl -X POST http://localhost:8000/admin/tenants/<guid>/wallet/topup \
  -H "Content-Type: application/json" \
  -d '{"credits": 1000, "note": "manual topup"}'
```

---

## 8. Pack fails to load — falls back to generic

**Symptom:** the tenant is using the wrong pack, or intent classification is wrong.

**Checklist:**
```bash
# Check whether the tenant has a pack assigned
docker exec -it docker-postgres-1 psql -U ai_admin -d ai_db -c "
SELECT * FROM ai_service.tenant_pack_assignments
WHERE company_guid = '<guid>';
"

# Clear the Redis cache if the pack data is stale
docker exec -it docker-redis-1 redis-cli DEL "pack:tourism@1.0.0"
```

---

## 9. Tool plugin doesn't load on startup

**Symptom:** the startup log doesn't show `tool.plugin.registered`.

**Checklist:**
- Does the class subclass `BaseTool`?
- Is the file located in `src/tools/plugins/`?
- Is there a syntax error in the import?

```bash
uv run python -c "from src.tools.loader import ToolPluginLoader; ToolPluginLoader.discover()"
```

---

## 10. Data lost after resetting the volume

**Symptom:** migrations pass but there's no data.

**Fix — re-seed:**
```bash
uv run python scripts/seed_pricing.py
uv run python scripts/seed_test_data.py
uv run python scripts/seed_packs.py
uv run python scripts/seed_tool_definitions.py
```

---

## 11. Anomaly alert — sudden spike for a tenant

**Symptom:** `GET /admin/usage/anomalies` returns a tenant with ratio > 3.

**Checklist:**
- Check usage details: `GET /admin/tenants/<guid>/usage`
- Check for abuse — review `audit_log`
- If you need to block the tenant, temporarily set `is_hard_stop = TRUE` and zero out the balance:

```bash
docker exec -it docker-postgres-1 psql -U ai_admin -d ai_db -c "
UPDATE ai_service.tenant_wallets
SET is_hard_stop = TRUE, balance = 0
WHERE company_guid = '<guid>';
"
```

---

## 12. RLS error — cross-tenant query

**Symptom:** `unrecognized configuration parameter app.current_tenant`

**Fix:** Make sure every query uses `acquire_with_tenant()`:
```python
async with DatabasePool.acquire_with_tenant(company_guid) as conn:
    # query here
```

---

## Rollback plan

| Situation | Time | How to roll back |
|---|---|---|
| New schema is broken | < 5 min | `uv run alembic downgrade -1` |
| App crashes after deploy | < 2 min | `git revert` + redeploy |
| Wallet system is broken | < 15 min | Set `USE_LEGACY_QUOTA=true` in `.env` |
| AI Service traffic is broken | < 15 min | Route back to the old n8n flow via the BE Private feature flag |
