"""Unified LLM wrapper: prompt template, retries, token accounting.

deepseek / openai / qwen share the OpenAI-compatible /chat/completions
protocol, called via stdlib urllib (no extra dependency). anthropic uses
the official SDK with prompt caching + json_schema structured output.
"""
import json
import logging
import time
import urllib.error
import urllib.request

from .config import resolve_api_key
from .prompts import NARRATIVE_SCHEMA, SYSTEM_PROMPT

log = logging.getLogger("vibetrace")

RETRYABLE_HTTP = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4
MAX_OUTPUT_TOKENS = 3000


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(self, cfg):
        self.provider = cfg["provider"]
        self.model = cfg["model"]
        self.base_url = ((cfg["providers"].get(self.provider) or {})
                         .get("base_url") or "").rstrip("/")
        self.api_key = resolve_api_key(cfg, self.provider)
        self.stats = {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                      "cache_hit_tokens": 0}
        if not self.api_key:
            raise LLMError(
                f"未配置 {self.provider} 的 API key:写入 ~/.vibetrace/config.json "
                f"的 providers.{self.provider}.api_key,或设置环境变量 "
                f"{self.provider.upper()}_API_KEY")

    def narrate(self, user_prompt, schema=NARRATIVE_SCHEMA,
                max_tokens=MAX_OUTPUT_TOKENS, system=None):
        """One structured-JSON completion. Raises LLMError on final failure.
        max_tokens 须覆盖『推理 + 输出』:推理模型(如 deepseek-v4-pro)会先花大量
        reasoning token,默认 3000 对复杂 schema(如课程分章)不够,调用方按需调大。
        system=None uses the default SYSTEM_PROMPT (narration); pass ASK_SYSTEM_PROMPT
        for grounded Q&A."""
        if self.provider == "anthropic":
            return self._anthropic(user_prompt, schema, max_tokens, system)
        return self._openai_compat(user_prompt, schema, max_tokens, system)

    def _openai_compat(self, user_prompt, schema, max_tokens, system=None):
        system = ((system or SYSTEM_PROMPT) + "\n\nJSON Schema:\n"
                  + json.dumps(schema, ensure_ascii=False))
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user_prompt}],
            "response_format": {"type": "json_object"},
            "max_tokens": max_tokens,
        }).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body, method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"})
        last_err = None
        for attempt in range(MAX_ATTEMPTS):
            if attempt:
                time.sleep(1.5 ** attempt)
            try:
                with urllib.request.urlopen(request, timeout=180) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                usage = data.get("usage") or {}
                self.stats["calls"] += 1
                self.stats["input_tokens"] += usage.get("prompt_tokens") or 0
                self.stats["output_tokens"] += usage.get("completion_tokens") or 0
                self.stats["cache_hit_tokens"] += usage.get("prompt_cache_hit_tokens") or 0
                content = data["choices"][0]["message"]["content"]
                return json.loads(content)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:200]
                last_err = f"HTTP {exc.code}: {detail}"
                if exc.code not in RETRYABLE_HTTP:
                    break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_err = f"网络错误:{exc}"
            except (KeyError, IndexError, json.JSONDecodeError) as exc:
                last_err = f"响应不符合预期:{exc}"  # 含非法 JSON 内容,重试一并覆盖
            log.warning("LLM 调用失败(第 %d 次):%s", attempt + 1, last_err)
        raise LLMError(f"{self.provider}/{self.model} 调用失败:{last_err}")

    def _anthropic(self, user_prompt, schema, max_tokens, system=None):
        try:
            import anthropic
        except ImportError as exc:
            raise LLMError("anthropic SDK 未安装:pip install anthropic") from exc
        client = anthropic.Anthropic(api_key=self.api_key, max_retries=3)
        try:
            resp = client.messages.create(
                model=self.model, max_tokens=max_tokens,
                system=[{"type": "text", "text": system or SYSTEM_PROMPT,
                         "cache_control": {"type": "ephemeral"}}],
                output_config={"format": {"type": "json_schema", "schema": schema}},
                messages=[{"role": "user", "content": user_prompt}])
        except anthropic.APIError as exc:
            raise LLMError(f"anthropic 调用失败:{exc}") from exc
        self.stats["calls"] += 1
        self.stats["input_tokens"] += resp.usage.input_tokens
        self.stats["output_tokens"] += resp.usage.output_tokens
        self.stats["cache_hit_tokens"] += resp.usage.cache_read_input_tokens or 0
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"anthropic 返回非法 JSON:{exc}") from exc
