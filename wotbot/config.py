import os
from dataclasses import dataclass
from typing import List, Optional


def _get_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "y"}


@dataclass
class Settings:
    # Twilio
    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_whatsapp_from: str = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    twilio_validate_signature: bool = _get_bool("TWILIO_VALIDATE_SIGNATURE", "false")
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "")

    # OpenAI
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    openai_use_responses: bool = _get_bool("OPENAI_USE_RESPONSES", "false")
    openai_use_assistants: bool = _get_bool("OPENAI_USE_ASSISTANTS", "false")
    openai_assistant_id: Optional[str] = os.getenv("OPENAI_ASSISTANT_ID")
    assistant_instructions: str = os.getenv(
        "ASSISTANT_INSTRUCTIONS",
        "You are WotBot, a WhatsApp assistant. Keep replies concise and mobile-friendly. Use tools when helpful. Prefer bullets and short paragraphs. If output is long, suggest summarizing.",
    )
    openai_temperature: float = float(os.getenv("OPENAI_TEMPERATURE", "0.3"))
    openai_max_tokens: int = int(os.getenv("OPENAI_MAX_TOKENS", "600"))

    # Admin & Modes
    admin_phone_numbers: List[str] = tuple(
        p.strip() for p in os.getenv("ADMIN_PHONE_NUMBERS", "").split(",") if p.strip()
    )

    # Tooling
    allow_http_domains: List[str] = tuple(
        d.strip() for d in os.getenv("ALLOW_HTTP_DOMAINS", "*").split(",") if d.strip()
    )
    code_exec_timeout_sec: int = int(os.getenv("CODE_EXEC_TIMEOUT_SEC", "5"))
    code_exec_memory_mb: int = int(os.getenv("CODE_EXEC_MEMORY_MB", "128"))
    http_timeout_sec: int = int(os.getenv("HTTP_TIMEOUT_SEC", "12"))

    # MCP servers (comma separated base URLs)
    mcp_servers: List[str] = tuple(
        s.strip() for s in os.getenv("MCP_SERVERS", "").split(",") if s.strip()
    )
    mcp_token: Optional[str] = os.getenv("MCP_TOKEN")

    # Security
    developer_mode_default: bool = _get_bool("DEVELOPER_MODE_DEFAULT", "false")

    # Admin web
    admin_web_username: str = os.getenv("ADMIN_WEB_USERNAME", "")
    admin_web_password: str = os.getenv("ADMIN_WEB_PASSWORD", "")

    # Overrides persistence
    overrides_path: str = os.getenv("OVERRIDES_PATH", "data/config/settings.json")

    # Filesystem
    logs_dir: str = os.getenv("LOGS_DIR", "logs")
    config_dir: str = os.getenv("CONFIG_DIR", "data/config")

    # Tools enablement
    enabled_tools: List[str] = tuple(
        t.strip() for t in os.getenv("ENABLED_TOOLS", "*").split(",") if t.strip()
    )


settings = Settings()


# Runtime overrides support
EDITABLE_FIELDS = {
    # OpenAI
    "OPENAI_API_KEY": ("openai_api_key", str),
    "OPENAI_MODEL": ("openai_model", str),
    "OPENAI_USE_RESPONSES": ("openai_use_responses", bool),
    "OPENAI_USE_ASSISTANTS": ("openai_use_assistants", bool),
    "OPENAI_ASSISTANT_ID": ("openai_assistant_id", str),
    # Twilio
    "TWILIO_ACCOUNT_SID": ("twilio_account_sid", str),
    "TWILIO_AUTH_TOKEN": ("twilio_auth_token", str),
    "TWILIO_WHATSAPP_FROM": ("twilio_whatsapp_from", str),
    "TWILIO_VALIDATE_SIGNATURE": ("twilio_validate_signature", bool),
    "PUBLIC_BASE_URL": ("public_base_url", str),
    # Tooling / Admin
    "ALLOW_HTTP_DOMAINS": ("allow_http_domains", list),
    "ADMIN_PHONE_NUMBERS": ("admin_phone_numbers", list),
    # MCP
    "MCP_SERVERS": ("mcp_servers", list),
    "MCP_TOKEN": ("mcp_token", str),
    # Assistant
    "ASSISTANT_INSTRUCTIONS": ("assistant_instructions", str),
    "OPENAI_TEMPERATURE": ("openai_temperature", float),
    "OPENAI_MAX_TOKENS": ("openai_max_tokens", int),
    # Tools
    "ENABLED_TOOLS": ("enabled_tools", list),
}


def _coerce_value(value: str, typ) -> object:
    if typ is bool:
        return str(value).lower() in {"1", "true", "yes", "y", "on"}
    if typ is list:
        return tuple(v.strip() for v in (value or "").split(",") if v.strip())
    if typ is int:
        try:
            return int(value)
        except Exception:
            return 0
    if typ is float:
        try:
            return float(value)
        except Exception:
            return 0.0
    return value


def apply_overrides(data: dict) -> None:
    for env_key, (attr, typ) in EDITABLE_FIELDS.items():
        if env_key in data:
            val = data[env_key]
            if isinstance(val, str):
                new_val = _coerce_value(val, typ)
            else:
                new_val = val
            setattr(settings, attr, new_val)


def load_overrides() -> dict:
    import json, os
    path = settings.overrides_path
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        apply_overrides(data)
        return data
    except Exception:
        return {}


def save_overrides(data: dict) -> None:
    import json, os
    os.makedirs(os.path.dirname(settings.overrides_path), exist_ok=True)
    with open(settings.overrides_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
