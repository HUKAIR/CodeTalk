"""Config loading and shared secret redaction for vibetrace."""
import copy
import json
import logging
import os
import re
from pathlib import Path

log = logging.getLogger("vibetrace")

VIBETRACE_DIR = Path.home() / ".vibetrace"
CONFIG_PATH = VIBETRACE_DIR / "config.json"
CACHE_DB_PATH = VIBETRACE_DIR / "cache.db"
USAGE_LOG_PATH = VIBETRACE_DIR / "usage.log"

DEFAULTS = {
    "vault_path": str(Path.home() / "vibetrace-reports"),
    "provider": "deepseek",
    "model": "deepseek-v4-pro",
    "diff_token_budget": 3000,
    "providers": {
        "deepseek": {"base_url": "https://api.deepseek.com/v1", "api_key": ""},
        "openai": {"base_url": "https://api.openai.com/v1", "api_key": ""},
        "qwen": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "api_key": ""},
        "anthropic": {"api_key": ""},
    },
}


def load_config():
    cfg = copy.deepcopy(DEFAULTS)
    try:
        user = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        for key, value in user.items():
            if key == "providers" and isinstance(value, dict):
                for name, pconf in value.items():
                    cfg["providers"].setdefault(name, {}).update(pconf or {})
            else:
                cfg[key] = value
    except FileNotFoundError:
        log.warning("config %s 不存在,使用默认配置", CONFIG_PATH)
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("config 读取失败(%s),使用默认配置", exc)
    return cfg


def resolve_api_key(cfg, provider):
    """Config file first, then <PROVIDER>_API_KEY env var."""
    key = (cfg["providers"].get(provider) or {}).get("api_key") or ""
    return key or os.environ.get(f"{provider.upper()}_API_KEY", "")


SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?:ghp|gho|ghs|github_pat)_[A-Za-z0-9_]{16,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._=-]{20,}"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)(\"?\s*[:=]\s*[\"']?)[A-Za-z0-9._-]{12,}"),
]


def redact_secrets(text):
    """Mask common secret patterns; applied before anything is persisted."""
    if not isinstance(text, str):
        return text
    for pat in SECRET_PATTERNS:
        text = pat.sub(lambda m: (m.group(1) + m.group(2) + "[REDACTED]")
                       if m.lastindex else "[REDACTED]", text)
    return text
