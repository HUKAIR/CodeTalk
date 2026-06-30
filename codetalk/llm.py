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

log = logging.getLogger("codetalk")

RETRYABLE_HTTP = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4
MAX_OUTPUT_TOKENS = 3000
MAX_TOKENS_CEIL = 8000      # 截断重试时 max_tokens 提升上限(抢救半截 JSON,封顶防失控)


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(self, cfg):
        if cfg.get("no_llm"):                     # 硬开关:显式关闭 LLM(数据不出本机)。
            raise LLMError(                        # 复用 LLMError → 各处现有降级路径自动生效。
                "已启用 no_llm(数据不出本机):LLM 调用被显式关闭。"
                "零-LLM 命令 blame/graph/search/brief/prompts 照常;"
                "digest 需 LLM 故跳过,ask/course/MCP ask 降级为确定性检索。"
                "关闭:config no_llm=false 或不设环境变量 CODETALK_NO_LLM。")
        self.provider = cfg["provider"]
        self.model = cfg["model"]
        pconf = cfg["providers"].get(self.provider) or {}
        self.base_url = (pconf.get("base_url") or "").rstrip("/")
        # 本地推理(ollama/LM Studio/llama.cpp,OpenAI 兼容)无需 key:local 标记或本机 base_url。
        # 数据不出本机由此从「除 LLM 例外」收紧到「连综合也可全本机」(local-first 真兑现,非主卖点)。
        self.local = (bool(pconf.get("local")) or "localhost" in self.base_url
                      or "127.0.0.1" in self.base_url)
        self.api_key = resolve_api_key(cfg, self.provider) or (
            "local" if self.local else "")
        self.output_lang = cfg.get("output_lang") or "中文"
        self.stats = {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                      "cache_hit_tokens": 0}
        if not self.api_key:
            raise LLMError(
                f"未配置 {self.provider} 的 API key:写入 ~/.codetalk/config.json "
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

    def chat(self, messages, max_tokens=MAX_OUTPUT_TOKENS):
        """多轮自由文本对话补全(非 JSON):接地材料已由调用方拼进 messages 并脱敏。
        → 答案字符串;失败抛 LLMError。no_llm 在 __init__ 已拦,到不了这里。"""
        if self.provider == "anthropic":
            return self._anthropic_chat(messages, max_tokens)
        return self._openai_chat(messages, max_tokens)

    def chat_stream(self, messages, max_tokens=MAX_OUTPUT_TOKENS):
        """流式对话补全 → 逐块 yield 文本 delta。接地材料已由调用方脱敏拼好。
        no_llm 在 __init__ 已拦。流式不重试(中途失败抛 LLMError,调用方可回退)。"""
        if self.provider == "anthropic":
            return self._anthropic_chat_stream(messages, max_tokens)
        return self._openai_chat_stream(messages, max_tokens)

    def _openai_chat_stream(self, messages, max_tokens):
        body = json.dumps({"model": self.model, "messages": messages,
                           "max_tokens": max_tokens, "stream": True}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body, method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"})
        try:
            with urllib.request.urlopen(request, timeout=180) as resp:
                for raw in resp:                       # 逐行读 text/event-stream
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        delta = json.loads(data)["choices"][0]["delta"].get("content")
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue                       # 心跳/异常块跳过,不崩
                    if delta:
                        yield delta
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
                OSError) as exc:
            raise LLMError(f"{self.provider}/{self.model} 流式失败:{exc}") from exc

    def _anthropic_chat_stream(self, messages, max_tokens):
        try:
            import anthropic
        except ImportError as exc:
            raise LLMError("anthropic SDK 未安装:pip install anthropic") from exc
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        turns = [m for m in messages if m["role"] != "system"]
        client = anthropic.Anthropic(api_key=self.api_key, max_retries=3)
        try:
            with client.messages.stream(model=self.model, max_tokens=max_tokens,
                                        system=system, messages=turns) as stream:
                yield from stream.text_stream
        except anthropic.APIError as exc:
            raise LLMError(f"anthropic 流式失败:{exc}") from exc

    def _openai_chat(self, messages, max_tokens):
        body = json.dumps({"model": self.model, "messages": messages,
                           "max_tokens": max_tokens}).encode("utf-8")
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
                usage = data.get("usage") or {}
                self.stats["calls"] += 1
                self.stats["input_tokens"] += usage.get("prompt_tokens") or 0
                self.stats["output_tokens"] += usage.get("completion_tokens") or 0
                return content
            except urllib.error.HTTPError as exc:
                last_err = f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:200]}"
                if exc.code not in RETRYABLE_HTTP:
                    break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_err = f"网络错误:{exc}"
            except (KeyError, IndexError, json.JSONDecodeError) as exc:
                last_err = f"响应不符合预期:{exc}"
            log.warning("LLM chat 调用失败(第 %d 次):%s", attempt + 1, last_err)
        raise LLMError(f"{self.provider}/{self.model} chat 调用失败:{last_err}")

    def _anthropic_chat(self, messages, max_tokens):
        try:
            import anthropic
        except ImportError as exc:
            raise LLMError("anthropic SDK 未安装:pip install anthropic") from exc
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        turns = [m for m in messages if m["role"] != "system"]
        client = anthropic.Anthropic(api_key=self.api_key, max_retries=3)
        try:
            resp = client.messages.create(model=self.model, max_tokens=max_tokens,
                                           system=system, messages=turns)
        except anthropic.APIError as exc:
            raise LLMError(f"anthropic chat 调用失败:{exc}") from exc
        self.stats["calls"] += 1
        self.stats["input_tokens"] += resp.usage.input_tokens
        self.stats["output_tokens"] += resp.usage.output_tokens
        return next((b.text for b in resp.content if b.type == "text"), "")

    def _openai_compat(self, user_prompt, schema, max_tokens, system=None,
                       cache_prefix=""):
        system = ((system or SYSTEM_PROMPT) + "\n\nJSON Schema:\n"
                  + json.dumps(schema, ensure_ascii=False))
        if cache_prefix:  # 稳定前缀置于 system 尾部,让 deepseek 自动前缀缓存命中
            system += "\n\n### 项目背景(节选,据此判断改动是否违背项目约束)\n" + cache_prefix
        cur_max = max_tokens                 # 截断时本调用内逐次提升(不改默认)
        last_err = None
        for attempt in range(MAX_ATTEMPTS):
            if attempt:
                time.sleep(1.5 ** attempt)
            body = json.dumps({                # 每次重建:截断重试用提升后的 cur_max
                "model": self.model,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user_prompt}],
                "response_format": {"type": "json_object"},
                "max_tokens": cur_max,
            }).encode("utf-8")
            request = urllib.request.Request(
                f"{self.base_url}/chat/completions", data=body, method="POST",
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {self.api_key}"})
            try:
                with urllib.request.urlopen(request, timeout=180) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                choice = data["choices"][0]
                # 截断:finish_reason==length → content 是半截 JSON,原样重试必再截,
                # 4 次烧 4 倍 token 且静默丢一条 commit。提 max_tokens 抢救(封顶,不无限涨)。
                if (choice.get("finish_reason") == "length"
                        and cur_max < MAX_TOKENS_CEIL):
                    cur_max = min(cur_max * 2, MAX_TOKENS_CEIL)
                    last_err = f"响应被 max_tokens 截断,提到 {cur_max} 重试"
                    log.warning("LLM 调用失败(第 %d 次):%s", attempt + 1, last_err)
                    continue
                result = json.loads(choice["message"]["content"])   # 解析成功再计数
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
