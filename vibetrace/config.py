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
    "output_lang": "中文",   # 叙事/回答的输出语言;英文项目可设 "English"
    "sources": ["claude"],   # 会话源;加 "cursor" 启用 Cursor(opt-in,数据仍不出本机)
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
    if not isinstance(cfg["providers"], dict):   # 非法 providers(标量/null)回退默认,免 LLMClient .get 崩
        log.warning("config.providers 类型非法,回退默认")
        cfg["providers"] = copy.deepcopy(DEFAULTS["providers"])
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
    re.compile(r"((?i:api[_-]?key|token|secret|password))(\"?\s*[:=]\s*[\"']?)(?=[A-Za-z0-9._-]*(?:[0-9]|[a-z][A-Z]|[A-Z][a-z]))[A-Za-z0-9._-]{12,}"),  # 关键词大小写不敏感;value 段须含数字或真实大小写转换(case-sensitive),降散文假阳又不漏 mixed-case key
    # 借 trivy builtin rules 扩充(故意不收 AWS 裸 40 位 base64 secret——假阳性灾难)
    re.compile(r"AIza[0-9A-Za-z_\-]{35}"),                              # Google API key
    re.compile(r"[0-9]+-[0-9A-Za-z_]{32}\.apps\.googleusercontent\.com"),  # Google OAuth
    re.compile(r"sk_(?:live|test)_[0-9a-zA-Z]{24}"),                    # Stripe
    re.compile(r"SG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}"),          # SendGrid
    re.compile(r"ey[A-Za-z0-9_\-]{17,}\.ey[A-Za-z0-9_\-]{17,}\.[A-Za-z0-9_\-]+"),  # JWT(签名段非空,降假阳性)
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),  # PEM 私钥整块
    re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/]+"),    # Slack webhook
]


def redact_secrets(text):
    """Mask common secret patterns; applied before anything is persisted."""
    if not isinstance(text, str):
        return text
    for pat in SECRET_PATTERNS:
        text = pat.sub(lambda m: (m.group(1) + m.group(2) + "[REDACTED]")
                       if m.lastindex else "[REDACTED]", text)
    return text
