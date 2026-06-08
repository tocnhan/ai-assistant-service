# HOW TO BUILD A TOOL PLUGIN

A guide for building a new tool plugin for the AI Assistant Service.
Read this carefully before coding — getting the architecture wrong from the start means a costly refactor later.

---

## Table of Contents

- [Architecture overview](#1-architecture-overview)
- [How it works](#2-how-it-works)
- [Creating a new plugin — step by step](#3-creating-a-new-plugin--step-by-step)
- [Real-world example](#4-real-world-example--bookinglookuptool)
- [Advanced plugin — with async init](#5-advanced-plugin--with-async-init)
- [Mandatory rules](#6-mandatory-rules)
- [Common pitfalls](#7-common-pitfalls)
- [Pre-merge checklist](#8-pre-merge-checklist)

---

## 1. Architecture overview

```
src/tools/
├── base.py                  ← BaseTool, ToolRegistry — DO NOT modify
├── loader.py                ← ToolPluginLoader — DO NOT modify
├── tool_logger.py           ← logs tool calls — DO NOT modify
└── plugins/
    ├── __init__.py
    ├── http_api_call.py     ← example plugin with runtime config
    ├── search_knowledge.py  ← example plugin using Qdrant
    └── web_search.py        ← example plugin calling an external API
```

**3 principles you must not violate:**

| Principle | Explanation |
|---|---|
| Code on the filesystem, config in the DB | `src/tools/plugins/` holds the code, `tool_definitions` holds the metadata, `tenant_tool_configs` holds the config — DO NOT store Python code in the DB |
| Same plugin, different config | A tourism tenant and an F&B tenant both use `http_api_call` but with a different `base_url` — don't create two separate plugins |
| `configure()` creates a new instance | Don't mutate the original instance in the registry — doing so will leak one tenant's config into another tenant's requests |

---

## 2. How it works

### Startup

```
uv run uvicorn src.main:app
    └── lifespan()
            └── ToolPluginLoader.discover()
                    └── scans src/tools/plugins/ (pkgutil.iter_modules)
                            └── imports each module
                                    └── finds classes that subclass BaseTool and have name != ""
                                            └── ToolRegistry.register(instance)
                                                    → logs: tool.plugin.registered
```

### On each /chat request

```
Orchestrator.run_stream()
    └── resolve_for_tenant() → EffectiveConfig.tool_whitelist = ["http_api_call", ...]
            └── ToolConfigService.get_tools_for_tenant(company_guid, whitelist)
                    └── queries tenant_tool_configs from the DB (RLS-filtered by tenant)
                            └── for each tool in the whitelist:
                                    ├── is_enabled = null  → use the default instance
                                    ├── is_enabled = false → skip — the agent won't see it
                                    └── is_enabled = true  → ToolRegistry.get_configured(name, config)
                                                                    └── tool.configure(config)
                                                                            → a new instance configured for this tenant
                    └── returns a list[BaseTool] that have been configured
            └── AgentRegistry.get_executor(..., tools=tools)
                    └── the LLM uses tools.to_mcp_spec() to learn how to call them
```

---

## 3. Creating a new plugin — step by step

### Step 1: Create the plugin file

Create a new file in `src/tools/plugins/`:

```
src/tools/plugins/your_tool_name.py
```

Name the file according to its function, using snake_case.

---

### Step 2: Write the plugin class

```python
# src/tools/plugins/your_tool_name.py
from src.tools.base import BaseTool


class YourToolNameTool(BaseTool):

    # ── 1. Metadata — the LLM reads this to decide when to call the tool ────

    name = "your_tool_name"
    # name must be unique across the whole system
    # must match tool_name in the tool_definitions table

    description = (
        "A short, clear description of what the tool does. "
        "The LLM reads this to decide whether to call the tool. "
        "The more specific, the better — e.g. 'Looks up an order's status by order code. "
        "Use this when the customer asks where their order is.'"
    )

    # JSON Schema of the INPUT — the LLM uses this to build the call payload
    input_schema = {
        "type": "object",
        "properties": {
            "required_param": {
                "type": "string",
                "description": "Describe clearly what this param is and what the LLM should fill in",
            },
            "optional_param": {
                "type": "integer",
                "description": "Description of the optional param",
                "default": 10,
            },
        },
        "required": ["required_param"],  # only list params that are truly required
    }

    # ── 2. Runtime config — default values, overridden by configure() ───────

    some_api_url: str = ""
    some_api_key: str = ""
    timeout: int = 10

    # ── 3. configure() — injects per-tenant config from the DB ──────────────

    def configure(self, config: dict) -> "YourToolNameTool":
        """
        Receives config from tenant_tool_configs.config in the DB.

        IMPORTANT:
        - Create a NEW instance — do not mutate self
        - Mutating self would leak tenant A's config into tenant B's requests
        - The config dict comes from the DB and is not pre-validated — use .get() with defaults

        Args:
            config: dict from tenant_tool_configs.config, e.g.:
                    {"some_api_url": "https://api.example.com", "timeout": 15}

        Returns:
            A new instance with the config applied
        """
        instance = YourToolNameTool()
        instance.some_api_url = config.get("some_api_url", "").rstrip("/")
        instance.some_api_key = config.get("some_api_key", "")
        instance.timeout = config.get("timeout", 10)
        return instance

    # ── 4. _run() — the tool's actual logic ──────────────────────────────────

    async def _run(
        self,
        required_param: str,
        optional_param: int = 10,
        tenant_id: str = None,   # injected from the middleware if needed — never let the LLM fill this in
    ) -> dict:
        """
        Write the real logic here.

        Rules:
        - ALWAYS return a dict
        - DO NOT raise exceptions when avoidable — return {"error": "..."} instead
        - Validate the config before using it
        - If you need tenant_id, inject it from the middleware — don't let the LLM fill it in
        """
        # Validate config first
        if not self.some_api_url:
            return {
                "error": "your_tool_name has not been configured with some_api_url for this tenant.",
                "success": False,
            }

        # ... real logic here ...

        return {
            "result": f"Processed result for {required_param}",
            "success": True,
        }
```

---

### Step 3: Seed `tool_definitions` into the DB

Open `scripts/seed_tool_definitions.py` and add a new entry to the `TOOL_DEFINITIONS` list:

```python
{
    "tool_name": "your_tool_name",             # must match BaseTool.name
    "display_name": "Display name for admin",  # shown to admins on the dashboard
    "description": "A fuller description for admins, not for the LLM.",
    "plugin_class": "src.tools.plugins.your_tool_name.YourToolNameTool",

    # config_schema — JSON Schema used to validate the admin's config before saving to the DB
    # this is the schema of the config dict passed into configure()
    "config_schema": {
        "type": "object",
        "required": ["some_api_url"],
        "properties": {
            "some_api_url": {
                "type": "string",
                "description": "API base URL, e.g. https://api.example.com",
            },
            "some_api_key": {
                "type": "string",
                "description": "API key for authentication",
            },
            "timeout": {
                "type": "integer",
                "default": 10,
                "description": "Timeout in seconds",
            },
        },
    },

    # input_schema — copy from the class for consistency
    # this is the schema the LLM uses to build the call payload
    "input_schema": {
        "type": "object",
        "required": ["required_param"],
        "properties": {
            "required_param": {
                "type": "string",
                "description": "Clear description",
            },
            "optional_param": {
                "type": "integer",
                "default": 10,
                "description": "Description of the optional param",
            },
        },
    },
},
```

Run the seed:

```bash
uv run python scripts/seed_tool_definitions.py
```

---

### Step 4: Add the tool to a pack's whitelist

Open `scripts/seed_packs.py`, find the pack you want to enable the tool for, and add it to `tool_whitelist`:

```python
"tool_whitelist": [
    "search_knowledge",
    "http_api_call",
    "your_tool_name",    # ← add it here
]
```

Re-run the pack seed:

```bash
uv run python scripts/seed_packs.py
```

> If a tenant is already using this pack — clear its Redis cache:
> ```bash
> docker exec -it docker-redis-1 redis-cli DEL "pack:tourism@1.0.0"
> ```

---

### Step 5: Enable the tool for a tenant via the API

Edit `scripts/test_body.json`:

```json
{"is_enabled": true, "config": {"some_api_url": "https://api.example.com", "timeout": 15}}
```

Generate the HMAC:

```bash
uv run python scripts/gen_hmac.py
```

Call the PUT endpoint:

```bash
# Windows
curl.exe -X PUT "http://localhost:8000/admin/tenants/<company_guid>/tools/your_tool_name" `
  -H "Content-Type: application/json" `
  -H "X-Company-GUID: <company_guid>" `
  -H "X-User-GUID: <user_guid>" `
  -H "X-Domain: <domain>" `
  -H "X-Timestamp: <timestamp>" `
  -H "X-Signature: <signature>" `
  -d "@scripts/test_body.json"

# Linux/Mac
curl -X PUT "http://localhost:8000/admin/tenants/<company_guid>/tools/your_tool_name" \
  -H "Content-Type: application/json" \
  ... \
  -d '@scripts/test_body.json'
```

---

### Step 6: Restart the app

```bash
uv run uvicorn src.main:app --reload
```

`ToolPluginLoader.discover()` automatically scans and registers the new plugin at startup — **no manual import needed anywhere**.

Check the startup log:

```
tool.plugin.registered  tool=your_tool_name  module=src.tools.plugins.your_tool_name
tool.plugin.discover_done  total=4
```

---

### Step 7: Verify

```bash
# Check the tool appears in the list
curl.exe -X GET "http://localhost:8000/admin/tools" ...

# Check the tool is enabled for the tenant
curl.exe -X GET "http://localhost:8000/admin/tenants/<guid>/tools" ...

# Check the MCP spec — only enabled tools should show
curl.exe -X GET "http://localhost:8000/admin/tenants/<guid>/tools/mcp-spec" ...
```

---

## 4. Real-world example — BookingLookupTool

A tool that looks up booking status by booking code, for the tourism vertical:

```python
# src/tools/plugins/booking_lookup.py
import httpx
from src.tools.base import BaseTool


class BookingLookupTool(BaseTool):
    name = "booking_lookup"
    description = (
        "Looks up booking information by booking code. "
        "Use this when the customer asks about their booking status, "
        "check-in date, or room information."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "booking_code": {
                "type": "string",
                "description": "The customer's booking code, e.g. BK-2026-001",
            },
        },
        "required": ["booking_code"],
    }

    api_base_url: str = ""
    api_token: str = ""
    timeout: int = 10

    def configure(self, config: dict) -> "BookingLookupTool":
        instance = BookingLookupTool()
        instance.api_base_url = config.get("api_base_url", "").rstrip("/")
        instance.api_token = config.get("api_token", "")
        instance.timeout = config.get("timeout", 10)
        return instance

    async def _run(self, booking_code: str, tenant_id: str = None) -> dict:
        if not self.api_base_url:
            return {
                "error": "booking_lookup has not been configured with api_base_url.",
                "success": False,
            }

        headers = {}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        if tenant_id:
            headers["X-Tenant-Id"] = tenant_id  # injected from the middleware

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.api_base_url}/api/bookings/{booking_code}",
                    headers=headers,
                )

                if response.status_code == 404:
                    return {
                        "found": False,
                        "message": f"Booking {booking_code} was not found.",
                        "success": True,
                    }

                response.raise_for_status()
                data = response.json()

                return {
                    "found": True,
                    "booking_code": booking_code,
                    "status": data.get("status"),
                    "check_in": data.get("check_in"),
                    "check_out": data.get("check_out"),
                    "room_type": data.get("room_type"),
                    "guest_name": data.get("guest_name"),
                    "success": True,
                }

            except httpx.TimeoutException:
                return {"error": "API timeout, please try again.", "success": False}
            except httpx.HTTPStatusError as e:
                return {"error": f"API error: {e.response.status_code}", "success": False}
```

Seed it into the DB:

```python
# Add to TOOL_DEFINITIONS in scripts/seed_tool_definitions.py
{
    "tool_name": "booking_lookup",
    "display_name": "Booking Lookup",
    "description": "Looks up booking information by booking code.",
    "plugin_class": "src.tools.plugins.booking_lookup.BookingLookupTool",
    "config_schema": {
        "type": "object",
        "required": ["api_base_url"],
        "properties": {
            "api_base_url": {"type": "string", "description": "Base URL of the booking API"},
            "api_token":    {"type": "string", "description": "Bearer token for authentication"},
            "timeout":      {"type": "integer", "default": 10},
        },
    },
    "input_schema": {
        "type": "object",
        "required": ["booking_code"],
        "properties": {
            "booking_code": {"type": "string", "description": "Booking code"},
        },
    },
},
```

---

## 5. Advanced plugin — with async init

If a plugin needs async initialization (e.g. connecting to a DB, loading a model), override the `async_init()` method:

```python
# src/tools/plugins/sql_query_safe.py
import asyncpg
from src.tools.base import BaseTool


class SqlQuerySafeTool(BaseTool):
    name = "sql_query_safe"
    description = "Runs read-only queries against the tenant's DB. SELECT only."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The SELECT query to run, e.g. SELECT * FROM orders LIMIT 10",
            },
        },
        "required": ["query"],
    }

    db_url: str = ""
    _pool: asyncpg.Pool = None   # not serialized into config

    def configure(self, config: dict) -> "SqlQuerySafeTool":
        instance = SqlQuerySafeTool()
        instance.db_url = config.get("db_url", "")
        return instance

    async def _run(self, query: str) -> dict:
        # Only allow SELECT — protects against destructive SQL injection
        query_stripped = query.strip().upper()
        if not query_stripped.startswith("SELECT"):
            return {
                "error": "Only SELECT queries are allowed.",
                "success": False,
            }

        if not self.db_url:
            return {"error": "sql_query_safe has not been configured with db_url.", "success": False}

        try:
            conn = await asyncpg.connect(self.db_url)
            rows = await conn.fetch(query)
            await conn.close()
            return {
                "rows": [dict(r) for r in rows],
                "count": len(rows),
                "success": True,
            }
        except Exception as e:
            return {"error": str(e), "success": False}
```

---

## 6. Mandatory rules

### Rule 1 — `configure()` MUST create a new instance

```python
# ❌ WRONG — mutates the original instance in the registry
# Tenant A's config will leak into tenant B's next request
def configure(self, config: dict) -> "MyTool":
    self.base_url = config.get("base_url", "")
    return self

# ✅ CORRECT — creates a new instance
def configure(self, config: dict) -> "MyTool":
    instance = MyTool()
    instance.base_url = config.get("base_url", "")
    return instance
```

### Rule 2 — `_run()` ALWAYS returns a dict

```python
# ❌ WRONG
async def _run(self, query: str):
    return "result string"   # the LLM can't parse this

async def _run(self, query: str):
    raise ValueError("error")  # crashes the agent

# ✅ CORRECT
async def _run(self, query: str) -> dict:
    return {"result": "the result", "success": True}

async def _run(self, query: str) -> dict:
    return {"error": "something went wrong", "success": False}
```

### Rule 3 — DO NOT hardcode secrets in the plugin

```python
# ❌ WRONG
class MyTool(BaseTool):
    api_key: str = "sk-hardcoded-key-123"   # leaks the key in the code

# ✅ CORRECT — read it from the config dict, set by the admin via the PUT endpoint
def configure(self, config: dict) -> "MyTool":
    instance = MyTool()
    instance.api_key = config.get("api_key", "")  # from tenant_tool_configs.config
    return instance
```

### Rule 4 — `tenant_id` is injected from the middleware, never filled in by the LLM

```python
# ❌ WRONG — the LLM could fill in a fake tenant_id
input_schema = {
    "properties": {
        "tenant_id": {"type": "string"},  # don't expose this to the LLM
    }
}

# ✅ CORRECT — accept tenant_id as a normal parameter but DO NOT declare it in input_schema
async def _run(self, query: str, tenant_id: str = None) -> dict:
    # tenant_id is injected from the middleware, not from the LLM
    headers = {"X-Tenant-Id": tenant_id} if tenant_id else {}
```

### Rule 5 — `name` must be unique and match the DB

```python
# Tool name in the class
class MyTool(BaseTool):
    name = "my_tool"   # ← must match

# tool_name in tool_definitions
INSERT INTO ai_service.tool_definitions (tool_name, ...)
VALUES ('my_tool', ...)  # ← must match

# tool_name in the pack whitelist
"tool_whitelist": ["my_tool"]  # ← must match
```

---

## 7. Common pitfalls

### The tool doesn't show up after creation

Check the startup log — if you don't see `tool.plugin.registered`:

```bash
# Run the app and check the log
uv run uvicorn src.main:app --reload
```

Common causes:
- The class doesn't subclass `BaseTool`
- `name` was left as an empty string `""`
- The file isn't located in `src/tools/plugins/`
- An import error in the file — check the syntax

```bash
# Manually test the import
uv run python -c "from src.tools.plugins.your_tool import YourTool; print(YourTool.name)"
```

---

### The tool doesn't appear in the MCP spec

```bash
# Check whether the tool is enabled
curl GET /admin/tenants/<guid>/tools
```

- `is_enabled: null` — not configured yet → call PUT to enable it
- `is_enabled: false` — disabled → call PUT with `is_enabled: true`
- The tool isn't in the list at all → `tool_name` is missing from the pack's `tool_whitelist`

---

### `configure()` doesn't seem to take effect

Check whether you're mutating `self`:

```python
# Debug — print the instance ids
def configure(self, config: dict) -> "MyTool":
    instance = MyTool()
    print(f"registry instance: {id(self)}, new instance: {id(instance)}")
    # These must be 2 different ids
    instance.base_url = config.get("base_url", "")
    return instance
```

---

### HMAC signature invalid when testing the PUT endpoint

The body must be a single line, with no newlines — fix `scripts/test_body.json`:

```json
{"is_enabled": true, "config": {"some_api_url": "https://api.example.com"}}
```

Then regenerate the HMAC:

```bash
uv run python scripts/gen_hmac.py
```

---

### RLS error when the tool queries the DB

A tool querying the AI service's own DB needs to set the tenant context within the transaction:

```python
async def _run(self, ...) -> dict:
    from src.db.session import DatabasePool
    async with DatabasePool._pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1::text, true)",
                self.company_guid,
            )
            rows = await conn.fetch(...)
```

---

### The tool gets registered twice

If you see the `tool.plugin.registered` log line twice for the same tool — check whether some old file in `src/tools/` (not `plugins/`) is importing and registering it.

Remove or comment out the registration line in the old file:

```python
# src/tools/search_tool.py — old file
# ToolRegistry.register(SearchTool())  ← comment out or delete this line
```

---

## 8. Pre-merge checklist

**Code:**
- [ ] The class subclasses `BaseTool` and has `name`, `description`, `input_schema`
- [ ] `name` is unique and doesn't clash with an existing tool
- [ ] `configure()` creates a new instance and doesn't mutate `self`
- [ ] `_run()` always returns a `dict`
- [ ] `_run()` handles an empty config gracefully — returns `{"error": "..."}` instead of crashing
- [ ] No hardcoded secrets or API keys in the code
- [ ] `tenant_id` is not declared in `input_schema`

**DB:**
- [ ] `tool_definitions` has been seeded — `uv run python scripts/seed_tool_definitions.py`
- [ ] `tool_name` in the DB exactly matches `BaseTool.name`
- [ ] `plugin_class` has the correct import path

**Pack:**
- [ ] `tool_name` has been added to the relevant pack's `tool_whitelist`
- [ ] `uv run python scripts/seed_packs.py` has been re-run
- [ ] The pack's Redis cache has been cleared if needed

**Tests:**
- [ ] Tested with at least 1 tenant that has the tool enabled → tool appears in the MCP spec
- [ ] Tested with 1 tenant that doesn't have it enabled → tool does not appear
- [ ] Tested `_run()` with a valid config → returns the correct result
- [ ] Tested `_run()` with an empty config → returns `{"error": "..."}`, doesn't crash

**Docs:**
- [ ] `README.md`'s Tool Plugin System section has been updated if needed
