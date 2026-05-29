# HOW TO BUILD A TOOL PLUGIN

Hướng dẫn tạo tool plugin mới cho AI Assistant Service.  
Đọc kỹ trước khi code — sai architecture từ đầu sẽ mất công refactor sau.

---

## Mục lục

- [Tổng quan kiến trúc](#1-tổng-quan-kiến-trúc)
- [Luồng hoạt động](#2-luồng-hoạt-động)
- [Tạo plugin mới — step by step](#3-tạo-plugin-mới--step-by-step)
- [Ví dụ thực tế](#4-ví-dụ-thực-tế--bookinglookuptool)
- [Plugin nâng cao — có async init](#5-plugin-nâng-cao--có-async-init)
- [Các rule bắt buộc](#6-các-rule-bắt-buộc)
- [Các lỗi thường gặp](#7-các-lỗi-thường-gặp)
- [Checklist trước khi merge](#8-checklist-trước-khi-merge)

---

## 1. Tổng quan kiến trúc

```
src/tools/
├── base.py                  ← BaseTool, ToolRegistry — KHÔNG sửa
├── loader.py                ← ToolPluginLoader — KHÔNG sửa
├── tool_logger.py           ← logging tool call — KHÔNG sửa
└── plugins/
    ├── __init__.py
    ├── http_api_call.py     ← ví dụ plugin có runtime config
    ├── search_knowledge.py  ← ví dụ plugin với Qdrant
    └── web_search.py        ← ví dụ plugin gọi external API
```

**3 nguyên tắc không được vi phạm:**

| Nguyên tắc | Giải thích |
|---|---|
| Code trên filesystem, config trong DB | `src/tools/plugins/` chứa code, `tool_definitions` chứa metadata, `tenant_tool_configs` chứa config — KHÔNG lưu Python code vào DB |
| Cùng plugin, khác config | Tenant du lịch và F&B dùng chung `http_api_call` nhưng `base_url` khác nhau — không tạo 2 plugin riêng |
| `configure()` tạo instance mới | Không mutate instance gốc trong registry — nếu mutate thì config của tenant này sẽ leak sang tenant khác |

---

## 2. Luồng hoạt động

### Startup

```
uv run uvicorn src.main:app
    └── lifespan()
            └── ToolPluginLoader.discover()
                    └── scan src/tools/plugins/ (pkgutil.iter_modules)
                            └── import từng module
                                    └── tìm class kế thừa BaseTool + có name != ""
                                            └── ToolRegistry.register(instance)
                                                    → log: tool.plugin.registered
```

### Mỗi request /chat

```
Orchestrator.run_stream()
    └── resolve_for_tenant() → EffectiveConfig.tool_whitelist = ["http_api_call", ...]
            └── ToolConfigService.get_tools_for_tenant(company_guid, whitelist)
                    └── query tenant_tool_configs từ DB (RLS lọc theo tenant)
                            └── với mỗi tool trong whitelist:
                                    ├── is_enabled = null  → dùng default instance
                                    ├── is_enabled = false → bỏ qua, agent không thấy
                                    └── is_enabled = true  → ToolRegistry.get_configured(name, config)
                                                                    └── tool.configure(config)
                                                                            → instance mới với config của tenant
                    └── trả về list[BaseTool] đã configured
            └── AgentRegistry.get_executor(..., tools=tools)
                    └── LLM dùng tools.to_mcp_spec() để biết cách gọi
```

---

## 3. Tạo plugin mới — step by step

### Bước 1: Tạo file plugin

Tạo file mới trong `src/tools/plugins/`:

```
src/tools/plugins/ten_tool_cua_ban.py
```

Đặt tên file theo chức năng, dùng snake_case.

---

### Bước 2: Viết class plugin

```python
# src/tools/plugins/ten_tool_cua_ban.py
from src.tools.base import BaseTool


class TenToolCuaBanTool(BaseTool):

    # ── 1. Metadata — LLM đọc để biết khi nào gọi tool này ──────────────────

    name = "ten_tool_cua_ban"
    # name phải unique trong toàn hệ thống
    # phải khớp với tool_name trong bảng tool_definitions

    description = (
        "Mô tả ngắn gọn, rõ ràng tool làm gì. "
        "LLM đọc cái này để quyết định có nên gọi tool không. "
        "Càng cụ thể càng tốt — ví dụ: 'Tra cứu trạng thái đơn hàng theo mã đơn. "
        "Dùng khi khách hỏi đơn hàng của họ đang ở đâu.'"
    )

    # JSON Schema của INPUT — LLM dùng để build payload khi gọi tool
    input_schema = {
        "type": "object",
        "properties": {
            "param_bat_buoc": {
                "type": "string",
                "description": "Mô tả rõ param này là gì, LLM sẽ điền gì vào đây",
            },
            "param_optional": {
                "type": "integer",
                "description": "Mô tả param optional",
                "default": 10,
            },
        },
        "required": ["param_bat_buoc"],  # chỉ list param thực sự bắt buộc
    }

    # ── 2. Runtime config — giá trị mặc định, sẽ bị override bởi configure() ─

    some_api_url: str = ""
    some_api_key: str = ""
    timeout: int = 10

    # ── 3. configure() — inject config per-tenant từ DB ──────────────────────

    def configure(self, config: dict) -> "TenToolCuaBanTool":
        """
        Nhận config từ tenant_tool_configs.config trong DB.

        QUAN TRỌNG:
        - Tạo instance MỚI — không mutate self
        - Nếu mutate self thì config tenant A sẽ leak sang tenant B
        - config dict đến từ DB, không validate trước — dùng .get() với default

        Args:
            config: dict từ tenant_tool_configs.config, ví dụ:
                    {"some_api_url": "https://api.example.com", "timeout": 15}

        Returns:
            Instance mới đã được configured
        """
        instance = TenToolCuaBanTool()
        instance.some_api_url = config.get("some_api_url", "").rstrip("/")
        instance.some_api_key = config.get("some_api_key", "")
        instance.timeout = config.get("timeout", 10)
        return instance

    # ── 4. _run() — logic thật của tool ──────────────────────────────────────

    async def _run(
        self,
        param_bat_buoc: str,
        param_optional: int = 10,
        tenant_id: str = None,   # inject từ middleware nếu cần, KHÔNG để LLM tự sinh
    ) -> dict:
        """
        Logic thật viết ở đây.

        Rules:
        - LUÔN trả về dict
        - KHÔNG raise exception nếu có thể tránh — trả về {"error": "..."} thay thế
        - Kiểm tra config hợp lệ trước khi dùng
        - tenant_id nếu cần thì inject từ middleware, không để LLM tự điền
        """
        # Kiểm tra config trước
        if not self.some_api_url:
            return {
                "error": "ten_tool_cua_ban chưa được cấu hình some_api_url cho tenant này.",
                "success": False,
            }

        # ... logic thật ...

        return {
            "result": f"Kết quả xử lý {param_bat_buoc}",
            "success": True,
        }
```

---

### Bước 3: Seed `tool_definitions` vào DB

Mở `scripts/seed_tool_definitions.py`, thêm entry mới vào list `TOOL_DEFINITIONS`:

```python
{
    "tool_name": "ten_tool_cua_ban",          # phải khớp BaseTool.name
    "display_name": "Tên hiển thị cho admin", # admin đọc trên dashboard
    "description": "Mô tả đầy đủ hơn cho admin, không phải cho LLM.",
    "plugin_class": "src.tools.plugins.ten_tool_cua_ban.TenToolCuaBanTool",

    # config_schema — JSON Schema validate config của admin trước khi lưu DB
    # đây là schema của config dict truyền vào configure()
    "config_schema": {
        "type": "object",
        "required": ["some_api_url"],
        "properties": {
            "some_api_url": {
                "type": "string",
                "description": "Base URL của API, ví dụ: https://api.example.com",
            },
            "some_api_key": {
                "type": "string",
                "description": "API key để authenticate",
            },
            "timeout": {
                "type": "integer",
                "default": 10,
                "description": "Timeout tính bằng giây",
            },
        },
    },

    # input_schema — copy từ class luôn cho nhất quán
    # đây là schema LLM dùng để build payload khi gọi tool
    "input_schema": {
        "type": "object",
        "required": ["param_bat_buoc"],
        "properties": {
            "param_bat_buoc": {
                "type": "string",
                "description": "Mô tả rõ ràng",
            },
            "param_optional": {
                "type": "integer",
                "default": 10,
                "description": "Mô tả param optional",
            },
        },
    },
},
```

Chạy seed:

```bash
uv run python scripts/seed_tool_definitions.py
```

---

### Bước 4: Thêm tool vào pack whitelist

Mở `scripts/seed_packs.py`, tìm pack muốn enable tool, thêm vào `tool_whitelist`:

```python
"tool_whitelist": [
    "search_knowledge",
    "http_api_call",
    "ten_tool_cua_ban",    # ← thêm vào đây
]
```

Chạy lại seed pack:

```bash
uv run python scripts/seed_packs.py
```

> Nếu tenant đang dùng pack này — xóa Redis cache của pack:
> ```bash
> docker exec -it docker-redis-1 redis-cli DEL "pack:tourism@1.0.0"
> ```

---

### Bước 5: Enable tool cho tenant qua API

Sửa `scripts/test_body.json`:

```json
{"is_enabled": true, "config": {"some_api_url": "https://api.example.com", "timeout": 15}}
```

Gen HMAC:

```bash
uv run python scripts/gen_hmac.py
```

Gọi PUT endpoint:

```bash
# Windows
curl.exe -X PUT "http://localhost:8000/admin/tenants/<company_guid>/tools/ten_tool_cua_ban" `
  -H "Content-Type: application/json" `
  -H "X-Company-GUID: <company_guid>" `
  -H "X-User-GUID: <user_guid>" `
  -H "X-Domain: <domain>" `
  -H "X-Timestamp: <timestamp>" `
  -H "X-Signature: <signature>" `
  -d "@scripts/test_body.json"

# Linux/Mac
curl -X PUT "http://localhost:8000/admin/tenants/<company_guid>/tools/ten_tool_cua_ban" \
  -H "Content-Type: application/json" \
  ... \
  -d '@scripts/test_body.json'
```

---

### Bước 6: Restart app

```bash
uv run uvicorn src.main:app --reload
```

`ToolPluginLoader.discover()` tự scan và register plugin mới khi startup — **không cần import thủ công ở đâu cả**.

Kiểm tra log startup:

```
tool.plugin.registered  tool=ten_tool_cua_ban  module=src.tools.plugins.ten_tool_cua_ban
tool.plugin.discover_done  total=4
```

---

### Bước 7: Verify

```bash
# Kiểm tra tool xuất hiện trong danh sách
curl.exe -X GET "http://localhost:8000/admin/tools" ...

# Kiểm tra tool đã enable cho tenant
curl.exe -X GET "http://localhost:8000/admin/tenants/<guid>/tools" ...

# Kiểm tra MCP spec — chỉ show tool đã enable
curl.exe -X GET "http://localhost:8000/admin/tenants/<guid>/tools/mcp-spec" ...
```

---

## 4. Ví dụ thực tế — BookingLookupTool

Tool tra cứu trạng thái booking theo mã đặt chỗ cho vertical du lịch:

```python
# src/tools/plugins/booking_lookup.py
import httpx
from src.tools.base import BaseTool


class BookingLookupTool(BaseTool):
    name = "booking_lookup"
    description = (
        "Tra cứu thông tin booking theo mã đặt chỗ. "
        "Dùng khi khách hỏi về trạng thái booking, ngày check-in, "
        "hoặc thông tin phòng của họ."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "booking_code": {
                "type": "string",
                "description": "Mã đặt chỗ của khách, ví dụ: BK-2026-001",
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
                "error": "booking_lookup chưa được cấu hình api_base_url.",
                "success": False,
            }

        headers = {}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        if tenant_id:
            headers["X-Tenant-Id"] = tenant_id  # inject từ middleware

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.api_base_url}/api/bookings/{booking_code}",
                    headers=headers,
                )

                if response.status_code == 404:
                    return {
                        "found": False,
                        "message": f"Không tìm thấy booking {booking_code}.",
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
                return {"error": "API timeout, vui lòng thử lại.", "success": False}
            except httpx.HTTPStatusError as e:
                return {"error": f"API lỗi: {e.response.status_code}", "success": False}
```

Seed vào DB:

```python
# Thêm vào TOOL_DEFINITIONS trong scripts/seed_tool_definitions.py
{
    "tool_name": "booking_lookup",
    "display_name": "Booking Lookup",
    "description": "Tra cứu thông tin booking theo mã đặt chỗ.",
    "plugin_class": "src.tools.plugins.booking_lookup.BookingLookupTool",
    "config_schema": {
        "type": "object",
        "required": ["api_base_url"],
        "properties": {
            "api_base_url": {"type": "string", "description": "Base URL của booking API"},
            "api_token":    {"type": "string", "description": "Bearer token để authenticate"},
            "timeout":      {"type": "integer", "default": 10},
        },
    },
    "input_schema": {
        "type": "object",
        "required": ["booking_code"],
        "properties": {
            "booking_code": {"type": "string", "description": "Mã đặt chỗ"},
        },
    },
},
```

---

## 5. Plugin nâng cao — có async init

Nếu plugin cần khởi tạo async (ví dụ: connect DB, load model), override method `async_init()`:

```python
# src/tools/plugins/sql_query_safe.py
import asyncpg
from src.tools.base import BaseTool


class SqlQuerySafeTool(BaseTool):
    name = "sql_query_safe"
    description = "Truy vấn dữ liệu read-only từ DB của tenant. Chỉ cho phép SELECT."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Câu SQL SELECT muốn truy vấn, ví dụ: SELECT * FROM orders LIMIT 10",
            },
        },
        "required": ["query"],
    }

    db_url: str = ""
    _pool: asyncpg.Pool = None   # không serialize vào config

    def configure(self, config: dict) -> "SqlQuerySafeTool":
        instance = SqlQuerySafeTool()
        instance.db_url = config.get("db_url", "")
        return instance

    async def _run(self, query: str) -> dict:
        # Chỉ cho phép SELECT — bảo vệ khỏi SQL injection destructive
        query_stripped = query.strip().upper()
        if not query_stripped.startswith("SELECT"):
            return {
                "error": "Chỉ cho phép câu truy vấn SELECT.",
                "success": False,
            }

        if not self.db_url:
            return {"error": "sql_query_safe chưa được cấu hình db_url.", "success": False}

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

## 6. Các rule bắt buộc

### Rule 1 — `configure()` PHẢI tạo instance mới

```python
# ❌ SAI — mutate instance gốc trong registry
# Config tenant A sẽ leak sang tenant B ở request tiếp theo
def configure(self, config: dict) -> "MyTool":
    self.base_url = config.get("base_url", "")
    return self

# ✅ ĐÚNG — tạo instance mới
def configure(self, config: dict) -> "MyTool":
    instance = MyTool()
    instance.base_url = config.get("base_url", "")
    return instance
```

### Rule 2 — `_run()` LUÔN trả về dict

```python
# ❌ SAI
async def _run(self, query: str):
    return "kết quả string"   # LLM không parse được

async def _run(self, query: str):
    raise ValueError("lỗi")  # crash agent

# ✅ ĐÚNG
async def _run(self, query: str) -> dict:
    return {"result": "kết quả", "success": True}

async def _run(self, query: str) -> dict:
    return {"error": "lỗi gì đó", "success": False}
```

### Rule 3 — KHÔNG hardcode secret trong plugin

```python
# ❌ SAI
class MyTool(BaseTool):
    api_key: str = "sk-hardcoded-key-123"   # lộ key trong code

# ✅ ĐÚNG — lấy từ config dict, admin set qua PUT endpoint
def configure(self, config: dict) -> "MyTool":
    instance = MyTool()
    instance.api_key = config.get("api_key", "")  # từ tenant_tool_configs.config
    return instance
```

### Rule 4 — `tenant_id` inject từ middleware, không để LLM điền

```python
# ❌ SAI — LLM có thể điền tenant_id giả
input_schema = {
    "properties": {
        "tenant_id": {"type": "string"},  # đừng expose cái này cho LLM
    }
}

# ✅ ĐÚNG — nhận tenant_id như parameter bình thường nhưng KHÔNG khai báo trong input_schema
async def _run(self, query: str, tenant_id: str = None) -> dict:
    # tenant_id được inject từ middleware, không phải từ LLM
    headers = {"X-Tenant-Id": tenant_id} if tenant_id else {}
```

### Rule 5 — `name` phải unique và khớp với DB

```python
# Tool name trong class
class MyTool(BaseTool):
    name = "my_tool"   # ← phải khớp

# tool_name trong tool_definitions
INSERT INTO ai_service.tool_definitions (tool_name, ...)
VALUES ('my_tool', ...)  # ← phải khớp

# tool_name trong pack whitelist
"tool_whitelist": ["my_tool"]  # ← phải khớp
```

---

## 7. Các lỗi thường gặp

### Tool không xuất hiện sau khi tạo

Kiểm tra log startup — nếu không thấy `tool.plugin.registered`:

```bash
# Chạy app và xem log
uv run uvicorn src.main:app --reload
```

Nguyên nhân thường gặp:
- Class không kế thừa `BaseTool`
- `name` bị để rỗng `""`
- File không nằm trong `src/tools/plugins/`
- Lỗi import trong file — kiểm tra syntax

```bash
# Test import thủ công
uv run python -c "from src.tools.plugins.ten_tool import TenTool; print(TenTool.name)"
```

---

### Tool không xuất hiện trong MCP spec

```bash
# Kiểm tra tool đã enable chưa
curl GET /admin/tenants/<guid>/tools
```

- `is_enabled: null` — chưa config → gọi PUT để enable
- `is_enabled: false` — bị disable → gọi PUT với `is_enabled: true`
- Tool không có trong list → `tool_name` trong pack `tool_whitelist` chưa có

---

### `configure()` không có tác dụng

Kiểm tra xem có đang mutate `self` không:

```python
# Debug — in ra id của instance
def configure(self, config: dict) -> "MyTool":
    instance = MyTool()
    print(f"registry instance: {id(self)}, new instance: {id(instance)}")
    # Phải là 2 id khác nhau
    instance.base_url = config.get("base_url", "")
    return instance
```

---

### Signature HMAC invalid khi test PUT endpoint

Body phải là 1 dòng, không có newline — sửa `scripts/test_body.json`:

```json
{"is_enabled": true, "config": {"some_api_url": "https://api.example.com"}}
```

Rồi gen lại HMAC:

```bash
uv run python scripts/gen_hmac.py
```

---

### RLS error khi tool query DB

Tool tự query DB của AI service cần set tenant context trong transaction:

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

### Tool bị register 2 lần

Nếu thấy log `tool.plugin.registered` 2 lần cho cùng 1 tool — kiểm tra xem có file cũ nào trong `src/tools/` (không phải `plugins/`) đang import và register không.

Xóa hoặc comment dòng register trong file cũ:

```python
# src/tools/search_tool.py — file cũ
# ToolRegistry.register(SearchTool())  ← comment hoặc xóa dòng này
```

---

## 8. Checklist trước khi merge

**Code:**
- [ ] Class kế thừa `BaseTool`, có `name`, `description`, `input_schema`
- [ ] `name` unique, không trùng với tool nào đã có
- [ ] `configure()` tạo instance mới, không mutate `self`
- [ ] `_run()` luôn trả về `dict`
- [ ] `_run()` xử lý trường hợp config rỗng — trả về `{"error": "..."}` thay vì crash
- [ ] Không hardcode secret, API key trong code
- [ ] `tenant_id` không khai báo trong `input_schema`

**DB:**
- [ ] Đã seed `tool_definitions` — `uv run python scripts/seed_tool_definitions.py`
- [ ] `tool_name` trong DB khớp chính xác với `BaseTool.name`
- [ ] `plugin_class` đúng đường dẫn import

**Pack:**
- [ ] Đã thêm `tool_name` vào `tool_whitelist` của pack liên quan
- [ ] Đã chạy lại `uv run python scripts/seed_packs.py`
- [ ] Đã clear Redis cache của pack nếu cần

**Test:**
- [ ] Đã test với ít nhất 1 tenant enable tool → tool xuất hiện trong MCP spec
- [ ] Đã test với 1 tenant không enable → tool không xuất hiện
- [ ] Đã test `_run()` với config hợp lệ → trả về kết quả đúng
- [ ] Đã test `_run()` với config rỗng → trả về `{"error": "..."}`, không crash

**Docs:**
- [ ] Đã cập nhật `README.md` phần Tool Plugin System nếu cần