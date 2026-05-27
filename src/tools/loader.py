# src/tools/loader.py
import importlib
import inspect
import pkgutil
import structlog
from src.tools.base import BaseTool, ToolRegistry

logger = structlog.get_logger()


class ToolPluginLoader:
    """
    Scan toàn bộ src/tools/plugins/ khi app startup,
    tự động import và register mọi class kế thừa BaseTool.
    Không cần import thủ công từng plugin.
    """

    @classmethod
    def discover(cls) -> None:
        """
        Gọi 1 lần duy nhất trong lifespan startup.
        Scan src/tools/plugins/, tìm mọi subclass của BaseTool,
        register vào ToolRegistry.
        """
        import src.tools.plugins as plugins_pkg

        discovered = 0

        for module_info in pkgutil.iter_modules(plugins_pkg.__path__):
            module_name = f"src.tools.plugins.{module_info.name}"
            try:
                module = importlib.import_module(module_name)
            except Exception as e:
                logger.error(
                    "tool.plugin.import_failed",
                    module=module_name,
                    error=str(e),
                )
                continue

            for _, obj in inspect.getmembers(module, inspect.isclass):
                # Chỉ lấy class con của BaseTool,
                # bỏ qua BaseTool chính nó và abstract class
                if (
                    issubclass(obj, BaseTool)
                    and obj is not BaseTool
                    and obj.__module__ == module_name
                    and bool(obj.name)  # bỏ qua class chưa đặt name
                ):
                    instance = obj()
                    ToolRegistry.register(instance)
                    discovered += 1
                    logger.info(
                        "tool.plugin.registered",
                        tool=obj.name,
                        module=module_name,
                    )

        logger.info("tool.plugin.discover_done", total=discovered)