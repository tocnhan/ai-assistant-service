# Industry Pack Guide

## What is a pack?

A pack is the configuration for a single vertical, immutable per version. Tenants choose a pack when they're onboarded.
Onboarding a new client = assign a pack + enable tools = done, no code required.

---

## Structure of a pack

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

## Available packs

| Pack | Vertical | Intents |
|---|---|---|
| `tourism@1.0.0` | Tourism, hotels | general_chat, search_knowledge, api_action, summarize |
| `generic@1.0.0` | General-purpose | general_chat, web_search |
| `spa_booking@1.0.0` | Spa, clinics | general_chat, api_action |

---

## Creating a new pack

### Step 1 — Create the pack via the API

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

### Step 2 — Create prompt templates

```bash
curl -X POST http://localhost:8000/admin/packs/templates \
  -H "Content-Type: application/json" \
  -d '{
    "pack_id": "fnb@1.0.0",
    "intent": "general_chat",
    "role": "system",
    "content": "You are the assistant for {{ tenant_name }}, specialized in helping F&B customers."
  }'
```

**Variables available in templates:**

| Variable | Description |
|---|---|
| `{{ tenant_name }}` | Tenant name |
| `{{ today }}` | Today's date |
| `{{ current_screen }}` | The user's current screen |
| `{{ business_rules }}` | The tenant's custom rules |

### Step 3 — Assign it to a tenant

```bash
curl -X POST http://localhost:8000/admin/tenants/assign-pack \
  -H "Content-Type: application/json" \
  -d '{"company_guid": "<guid>", "pack_id": "fnb@1.0.0"}'
```

---

## Tenant overrides

A tenant can override the pack defaults without affecting the original pack:

```json
{
  "prompts": {
    "general_chat:system": "This tenant's custom prompt..."
  },
  "default_models": {
    "executor": {"provider": "anthropic", "model": "claude-haiku-4-5"}
  },
  "extra_tools": ["web_search"]
}
```

---

## Version management

Packs are immutable — to make changes you must create a new version:

```
tourism@1.0.0  →  tourism@1.1.0  →  tourism@2.0.0
```

A tenant pins a specific version; upgrading requires explicitly re-assigning the pack.

---

## Clearing the pack cache

After updating a template, clear the Redis cache to make it take effect immediately:

```bash
docker exec -it docker-redis-1 redis-cli DEL "pack:tourism@1.0.0"
```
