# src/packs/template_engine.py
import logging
from datetime import date
from jinja2 import Environment, BaseLoader, StrictUndefined

log = logging.getLogger(__name__)

_jinja_env = Environment(
    loader=BaseLoader(),
    undefined=StrictUndefined,
    autoescape=False,
)


def render_prompt(template_text: str, context: dict) -> str:
    try:
        tmpl = _jinja_env.from_string(template_text)
        return tmpl.render(**context)
    except Exception as e:
        logging.exception(f"Template render error: {e} | template: {template_text[:100]}")
        return template_text  # fallback về template thô, không crash request


def build_context(
    tenant_name: str,
    current_screen: str | None = None,
    business_rules: str | None = None,
    extra: dict | None = None,
) -> dict:
    ctx = {
        "tenant_name": tenant_name,
        "today": date.today().isoformat(),
        "current_screen": current_screen or "không xác định",
        "business_rules": business_rules or "",
    }
    if extra:
        ctx.update(extra)
    return ctx