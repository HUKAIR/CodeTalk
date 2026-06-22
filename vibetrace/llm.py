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
        self.output_lang = cfg.get("output_lang") or "中文"
        self.stats = {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                      "cache_hit_tokens": 0}
        if not self.api_key:
            raise LLMError(
                f"未配置 {self.provider} 的 API key:写入 ~/.vibetrace/config.json "
                f"的 providers.{self.provider}.api_key,或设置环境变量 "
                f"{self.provider.upper()}_API_KEY")

    def narrate(self, user_prompt, schema=NARRATIVE_SCHEMA,
                max_tokens=MAX_OUTPUT_TOKENS, system=None, cache_prefix=""):
        """One structured-JSON completion. Raises LLMError on final failure.
        max_tokens 须覆盖『推理 + 输出』:推理模型(如 deepseek-v4-pro)会先花大量
        reasoning token,默认 3000 对复杂 schema(如课程分章)不够,调用方按需调大。
        system=None uses the default SYSTEM_PROMPT (narration); pass ASK_SYSTEM_PROMPT
        for grounded Q&A. 输出语言由 output_lang 决定(单一注入点)。
        cache_prefix:跨多次调用稳定的项目上下文(CLAUDE.md/README),作缓存前缀——
        anthropic 走第二个带 cache_control 的 system 块,openai-compat 拼进 system 消息
        让 deepseek 自动前缀缓存命中,避免每 commit 重传背景。"""
        sys = (system or SYSTEM_PROMPT) + f"\n所有输出字段用{self.output_lang}书写。"
        if self.provider == "anthropic":
            return self._anthropic(user_prompt, schema, max_tokens, sys, cache_prefix)
        return self._openai_compat(user_prompt, schema, max_tokens, sys, cache_prefix)

    def _openai_compat(self, user_prompt, schema, max_tokens, system=None,
                       cache_prefix=""):
        system = ((system or SYSTEM_PROMPT) + "\n\nJSON Schema:\n"
                  + json.dumps(schema, ensure_ascii=False))
        if cache_prefix:  # 稳定前缀置于 system 尾部,让 deepseek 自动前缀缓存命中
            system += "\n\n### 项目背景(节选,据此判断改动是否违背项目约束)\n" + cache_prefix
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
                content = data["choices"][0]["message"]["content"]
                result = json.loads(content)   # 先解析成功再计数,失败重试不重复累加
                usage = data.get("usage") or {}
                self.stats["calls"] += 1
                self.stats["input_tokens"] += usage.get("prompt_tokens") or 0
                self.stats["output_tokens"] += usage.get("completion_tokens") or 0
                self.stats["cache_hit_tokens"] += usage.get("prompt_cache_hit_tokens") or 0
                return result
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

    def _anthropic(self, user_prompt, schema, max_tokens, system=None,
                   cache_prefix=""):
        try:
            import anthropic
        except ImportError as exc:
            raise LLMError("anthropic SDK 未安装:pip install anthropic") from exc
        client = anthropic.Anthropic(api_key=self.api_key, max_retries=3)
        system_blocks = [{"type": "text", "text": system or SYSTEM_PROMPT,
                          "cache_control": {"type": "ephemeral"}}]
        if cache_prefix:  # 项目上下文作第二个缓存前缀块,不随 commit 变、命中后近乎免费
            system_blocks.append({"type": "text", "text": cache_prefix,
                                  "cache_control": {"type": "ephemeral"}})
        try:
            resp = client.messages.create(
                model=self.model, max_tokens=max_tokens,
                system=system_blocks,
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
