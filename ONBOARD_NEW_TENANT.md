# Onboard New Tenant

## Step 1 — Create the tenant

```bash
docker exec -it docker-postgres-1 psql -U ai_admin -d ai_db -c "
INSERT INTO ai_service.tenants (company_guid, domain, plan)
VALUES ('<guid>', 'https://tenant-domain.com', 'pro');
"
```

## Step 2 — Add the allowed domain

```bash
docker exec -it docker-postgres-1 psql -U ai_admin -d ai_db -c "
INSERT INTO ai_service.allowed_domains (company_guid, domain, is_active)
VALUES ('<guid>', 'https://tenant-domain.com', TRUE);
"
```

## Step 3 — Assign an industry pack

```bash
curl -X POST http://localhost:8000/admin/tenants/assign-pack \
  -H "Content-Type: application/json" \
  -d '{"company_guid": "<guid>", "pack_id": "tourism@1.0.0"}'
```

Available packs: `tourism@1.0.0`, `generic@1.0.0`, `spa_booking@1.0.0`

## Step 4 — Set up the wallet

```bash
curl -X POST http://localhost:8000/admin/tenants/<guid>/wallet/topup \
  -H "Content-Type: application/json" \
  -d '{"credits": 10000, "note": "initial grant"}'
```

## Step 5 — Enable tools (optional)

```bash
curl -X PUT http://localhost:8000/admin/tenants/<guid>/tools/http_api_call \
  -H "Content-Type: application/json" \
  -d '{"is_enabled": true, "config": {"base_url": "https://api.tenant.com", "timeout": 15}}'
```

## Step 6 — Test

```bash
uv run python scripts/gen_hmac.py
# Use the generated signature to test /chat/stream
```

## Done ✅

The tenant is ready to go — no redeploy needed.
