# Onboard New Tenant

## Bước 1 — Tạo tenant

```bash
docker exec -it docker-postgres-1 psql -U ai_admin -d ai_db -c "
INSERT INTO ai_service.tenants (company_guid, domain, plan)
VALUES ('<guid>', 'https://tenant-domain.com', 'pro');
"
```

## Bước 2 — Thêm allowed domain

```bash
docker exec -it docker-postgres-1 psql -U ai_admin -d ai_db -c "
INSERT INTO ai_service.allowed_domains (company_guid, domain, is_active)
VALUES ('<guid>', 'https://tenant-domain.com', TRUE);
"
```

## Bước 3 — Assign industry pack

```bash
curl -X POST http://localhost:8000/admin/tenants/assign-pack \
  -H "Content-Type: application/json" \
  -d '{"company_guid": "<guid>", "pack_id": "tourism@1.0.0"}'
```

Pack có sẵn: `tourism@1.0.0`, `generic@1.0.0`, `spa_booking@1.0.0`

## Bước 4 — Tạo wallet

```bash
curl -X POST http://localhost:8000/admin/tenants/<guid>/wallet/topup \
  -H "Content-Type: application/json" \
  -d '{"credits": 10000, "note": "initial grant"}'
```

## Bước 5 — Enable tools (optional)

```bash
curl -X PUT http://localhost:8000/admin/tenants/<guid>/tools/http_api_call \
  -H "Content-Type: application/json" \
  -d '{"is_enabled": true, "config": {"base_url": "https://api.tenant.com", "timeout": 15}}'
```

## Bước 6 — Test

```bash
uv run python scripts/gen_hmac.py
# Dùng signature vừa gen để test /chat/stream
```

## Done ✅

Tenant sẵn sàng, không cần deploy lại.