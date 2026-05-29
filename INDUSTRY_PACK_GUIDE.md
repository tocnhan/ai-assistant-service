# Industry Pack Guide

## Pack là gì?

Pack là config cho 1 vertical, immutable theo version. Tenant chọn pack khi onboard.
Onboard khách mới = assign pack + enable tools = xong, không cần code.

---

## Cấu trúc 1 pack

```
Pack tourism@1.0.0
├── intents: [general_chat, search_knowledge, api_action, summarize]
├── tool_whitelist: [search_knowledge, http_api_call]
├── default_models:
│   ├── classifier: groq/llama-3.1-8b-instant
│   └── executor: deepseek/deepseek-chat
└── prompt_templates:
    ├── general_chat:system
    └── api_action:system
```

---

## Pack có sẵn

| Pack | Vertical | Intents |
|---|---|---|
| `tourism@1.0.0` | Du lịch, khách sạn | general_chat, search_knowledge, api_action, summarize |
| `generic@1.0.0` | Tổng quát | general_chat, web_search |
| `spa_booking@1.0.0` | Spa, clinic | general_chat, api_action |

---

## Tạo pack mới

### Bước 1 — Tạo pack qua API

```bash
curl -X POST http://localhost:8000/admin/packs \
  -H "Content-Type: application/json" \
  -d '{
    "pack_id": "fnb@1.0.0",
    "display_name": "F&B Assistant",
    "intents": ["general_chat", "api_action", "search_knowledge"],
    "tool_whitelist": ["http_api_call", "search_knowledge"],
    "default_models": {
      "classifier": {"provider": "groq", "model": "llama-3.1-8b-instant"},
      "executor": {"provider": "deepseek", "model": "deepseek-chat"}
    }
  }'
```

### Bước 2 — Tạo prompt templates

```bash
curl -X POST http://localhost:8000/admin/packs/templates \
  -H "Content-Type: application/json" \
  -d '{
    "pack_id": "fnb@1.0.0",
    "intent": "general_chat",
    "role": "system",
    "content": "Bạn là trợ lý của {{ tenant_name }}, chuyên hỗ trợ khách hàng F&B."
  }'
```

**Biến có thể dùng trong template:**

| Biến | Mô tả |
|---|---|
| `{{ tenant_name }}` | Tên tenant |
| `{{ today }}` | Ngày hôm nay |
| `{{ current_screen }}` | Màn hình hiện tại của user |
| `{{ business_rules }}` | Rule riêng của tenant |

### Bước 3 — Assign cho tenant

```bash
curl -X POST http://localhost:8000/admin/tenants/assign-pack \
  -H "Content-Type: application/json" \
  -d '{"company_guid": "<guid>", "pack_id": "fnb@1.0.0"}'
```

---

## Tenant override

Tenant có thể override pack default mà không ảnh hưởng pack gốc:

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

## Version management

Pack immutable — muốn thay đổi phải tạo version mới:

```
tourism@1.0.0  →  tourism@1.1.0  →  tourism@2.0.0
```

Tenant pin version cụ thể, muốn upgrade phải explicit assign lại.

---

## Xóa cache pack

Sau khi update template, xóa Redis cache để có hiệu lực ngay:

```bash
docker exec -it docker-redis-1 redis-cli DEL "pack:tourism@1.0.0"
```