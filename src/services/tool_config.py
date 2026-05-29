# src/services/tool_config.py
import structlog
from src.db.session import DatabasePool
from src.tools.base import BaseTool, ToolRegistry

logger = structlog.get_logger()


class ToolConfigService:
    """
    Load config tool per-tenant từ DB,
    trả về list BaseTool đã được configure() với config của tenant đó.
    """

    @classmethod
    async def get_tools_for_tenant(
        cls,
        company_guid: str,
        whitelist: list[str],
    ) -> list[BaseTool]:
        """
        Lấy các tool trong whitelist của pack,
        filter chỉ những tool tenant đã enable,
        inject config từ tenant_tool_configs vào từng tool.

        Args:
            company_guid: UUID tenant
            whitelist: danh sách tool_name từ EffectiveConfig.tool_whitelist

        Returns:
            List BaseTool đã configured, sẵn sàng dùng
        """
        if not whitelist:
            return []

        try:
            async with DatabasePool._pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "SELECT set_config('app.current_tenant', $1::text, true)",
                        str(company_guid),
                    )
                    rows = await conn.fetch(
                        """
                        SELECT tool_name, is_enabled, config
                        FROM ai_service.tenant_tool_configs
                        WHERE company_guid = $1::uuid
                        AND tool_name = ANY($2::varchar[])
                        """,
                        company_guid,
                        whitelist,
                    )
        except Exception as e:
            logger.error("tool_config.load_failed", error=str(e), company_guid=company_guid)
            rows = []

        # Build lookup: tool_name -> {is_enabled, config}
        db_configs: dict[str, dict] = {}
        for row in rows:
            db_configs[row["tool_name"]] = {
                "is_enabled": row["is_enabled"],
                "config": row["config"] or {},
            }

        tools = []
        for tool_name in whitelist:
            # Tool không có trong ToolRegistry thì bỏ qua
            if tool_name not in ToolRegistry._tools:
                logger.warning("tool_config.not_registered", tool=tool_name)
                continue

            db_cfg = db_configs.get(tool_name)

            # Tool chưa có row trong tenant_tool_configs → dùng default, vẫn enable
            if db_cfg is None:
                tool = ToolRegistry.get(tool_name)
                tools.append(tool)
                logger.info("tool_config.default", tool=tool_name, company_guid=company_guid)
                continue

            # Tool bị tenant disable → bỏ qua
            if not db_cfg["is_enabled"]:
                logger.info("tool_config.disabled", tool=tool_name, company_guid=company_guid)
                continue

            # Inject config vào tool — trả về instance mới, không mutate registry
            config = db_cfg["config"]

            # Đặc biệt: search_knowledge tự động fallback collection về {guid}_docs
            if tool_name == "search_knowledge" and not config.get("collection"):
                config = {**config, "collection": f"{company_guid}_docs"}

            tool = ToolRegistry.get_configured(tool_name, config)
            tools.append(tool)
            logger.info("tool_config.configured", tool=tool_name, company_guid=company_guid)

        return tools