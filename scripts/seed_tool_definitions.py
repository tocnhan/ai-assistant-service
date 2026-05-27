# scripts/seed_tool_definitions.py
import asyncio
import asyncpg
from dotenv import load_dotenv
import os
import json

load_dotenv()

TOOL_DEFINITIONS = [
    {
        "tool_name": "http_api_call",
        "display_name": "HTTP API Call",
        "description": "Gọi HTTP API của hệ thống. Dùng để thực hiện các thao tác booking, tạo đơn, cập nhật dữ liệu.",
        "plugin_class": "src.tools.plugins.http_api_call.HttpApiCallTool",
        "config_schema": {
            "type": "object",
            "properties": {
                "base_url": {
                    "type": "string",
                    "description": "Base URL của API, ví dụ: https://api.booking.vn"
                },
                "headers": {
                    "type": "object",
                    "description": "HTTP headers mặc định, ví dụ: Authorization"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout tính bằng giây, mặc định 10",
                    "default": 10
                },
            },
            "required": ["base_url"],
        },
        "input_schema": {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "PATCH"],
                    "description": "HTTP method",
                },
                "path": {
                    "type": "string",
                    "description": "API path, ví dụ: /api/bookings",
                },
                "body": {
                    "type": "object",
                    "description": "Request body cho POST/PUT/PATCH",
                },
            },
            "required": ["method", "path"],
        },
    },
    {
        "tool_name": "search_knowledge",
        "display_name": "Search Knowledge Base",
        "description": "Tìm kiếm thông tin trong knowledge base của tenant.",
        "plugin_class": "src.tools.plugins.search_knowledge.SearchKnowledgeTool",
        "config_schema": {
            "type": "object",
            "properties": {
                "collection": {
                    "type": "string",
                    "description": "Qdrant collection name. Để trống thì tự fallback về {company_guid}_docs"
                },
                "top_k_default": {
                    "type": "integer",
                    "description": "Số kết quả mặc định, default 5",
                    "default": 5
                },
            },
        },
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Câu truy vấn tìm kiếm",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Số kết quả trả về",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "tool_name": "web_search",
        "display_name": "Web Search",
        "description": "Tìm kiếm thông tin trên internet qua Tavily API.",
        "plugin_class": "src.tools.plugins.web_search.WebSearchTool",
        "config_schema": {
            "type": "object",
            "properties": {
                "api_key": {
                    "type": "string",
                    "description": "Tavily API key"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Số kết quả tối đa, default 5",
                    "default": 5
                },
            },
            "required": ["api_key"],
        },
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Câu truy vấn tìm kiếm",
                },
            },
            "required": ["query"],
        },
    },
]


async def seed():
    dsn = os.environ["DATABASE_ADMIN_URL"].replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)

    for tool in TOOL_DEFINITIONS:
        await conn.execute(
            """
            INSERT INTO ai_service.tool_definitions
                (tool_name, display_name, description, plugin_class, config_schema, input_schema)
            VALUES
                ($1, $2, $3, $4, $5::jsonb, $6::jsonb)
            ON CONFLICT (tool_name) DO UPDATE SET
                display_name  = EXCLUDED.display_name,
                description   = EXCLUDED.description,
                plugin_class  = EXCLUDED.plugin_class,
                config_schema = EXCLUDED.config_schema,
                input_schema  = EXCLUDED.input_schema,
                updated_at    = NOW()
            """,
            tool["tool_name"],
            tool["display_name"],
            tool["description"],
            tool["plugin_class"],
            json.dumps(tool["config_schema"]),
            json.dumps(tool["input_schema"]),
        )
        print(f"✓ seeded: {tool['tool_name']}")

    await conn.close()
    print("\nDone! Tool definitions seeded.")


asyncio.run(seed())