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
    "no_llm": False,         # 硬开关:置 true 则显式关闭一切 LLM 调用(数据不出本机,连 LLM 例外也关)
    "providers": {
        "deepseek": {"base_url": "https://api.deepseek.com/v1", "api_key": ""},
        "openai": {"base_url": "https://api.openai.com/v1", "api_key": ""},
        "qwen": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "api_key": ""},
        "anthropic": {"api_key": ""},
        # 本地推理(零-egress):Ollama/LM Studio/llama.cpp 等 OpenAI 兼容端点,无需 key
        "ollama": {"base_url": "http://localhost:11434/v1", "api_key": "ollama", "local": True},
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
    if os.environ.get("VIBETRACE_NO_LLM"):       # 环境变量硬关 LLM(数据不出本机),一次性覆盖
        cfg["no_llm"] = True
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


def redact_data(obj):
    """递归脱敏 JSON-able 结构的字符串叶子;用在 json.dumps / HTML 编码之前。
    编码会把 " 转义成 \\" 等,使 redact_secrets 的 key="value" 定界模式匹配不到,
    故 secret 必须在「未编码的原始连续文本」上脱敏。非字符串叶子原样返回。"""
    if isinstance(obj, str):
        return redact_secrets(obj)
    if isinstance(obj, list):
        return [redact_data(x) for x in obj]
    if isinstance(obj, dict):
        return {k: redact_data(v) for k, v in obj.items()}
    return obj
