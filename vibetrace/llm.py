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

log = logging.getLogger("vibetrace")

RETRYABLE_HTTP = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4
MAX_OUTPUT_TOKENS = 3000

SYSTEM_PROMPT = (
    "你是 vibetrace 的代码变更叙事引擎。基于 git commit(message、stat、diff 节选)"
    "与关联的 Claude Code 会话摘录,为开发者本人生成中文叙事,帮他几天后快速回忆"
    "“AI 替我做了什么、为什么”。\n"
    "事实纪律(最高优先级):\n"
    "- what/why/decisions 只能陈述材料中有直接依据的事实;每条 decision 必须能"
    "对应 diff 中的具体改动或会话中的明确陈述,宁可少写、不可编造\n"
    "- 禁止使用材料中不存在的专有名词、文件名、函数名、数字\n"
    "- 禁止张冠李戴:不得把材料中 A 文件/A 角色/A 模块的行为说成 B 的"
    "(例如把 user 消息解析逻辑说成 assistant 的)\n"
    "- risks/open_loops 是你的推断,允许合理推测,但推断的前提必须与材料一致\n"
    "- 推断的列表字段(decisions/risks/open_loops)若确无依据,返回空数组 [],"
    "不要写“材料不足”之类占位;what/why 必填,只据材料、不足时 why 标“(推测)”\n"
    "文风纪律(去 AI 腔、让人愿读):\n"
    "- 不用开场陈词(「值得注意的是」「事实上」「总的来说」),直接说事\n"
    "- 不用破折号堆从句;不用「不是 X,而是 Y」的二元对照腔;不写凑数的三项排比\n"
    "- 被动改主动并点名施动者(user/assistant/哪个 commit);空泛形容词换成具体事实与数字\n"
    "输出必须是符合给定 JSON Schema 的单个 JSON 对象,不要输出任何其他文字。"
)

ASK_SYSTEM_PROMPT = (
    "你是 vibetrace 的单代码问答引擎。基于给定材料(这段代码相关 commit 的叙事 + 决策"
    "面包屑,旧→新),用中文回答开发者关于这段代码的问题。\n"
    "事实纪律(最高优先级):\n"
    "- 只用给定材料作答;材料不足以回答就直说『材料不足』,不补全、不编造\n"
    "- 信息优先级:① commit 叙事 ② 决策面包屑(旧→新) ③ 你的推断(须标『推测』);"
    "多条材料冲突时以最新的 commit 为准\n"
    "- 禁止编造材料中不存在的文件名/SHA/数字/专有名词\n"
    "- 在 cited_shas 里列出你实际据以回答的 commit 短 SHA\n"
    "- 没把握的部分写进 unsure,不要混进 answer 充数\n"
    "输出必须是符合给定 JSON Schema 的单个 JSON 对象,不要输出任何其他文字。"
)

ASK_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string", "description": "对问题的回答,只据材料"},
        "cited_shas": {"type": "array", "items": {"type": "string"},
                       "description": "实际据以回答的 commit 短 SHA"},
        "unsure": {"type": "string", "description": "没把握/材料不足之处,可空"},
    },
    "required": ["answer", "cited_shas"],
    "additionalProperties": False,
}

NARRATIVE_SCHEMA = {
    "type": "object",
    "properties": {
        "what": {"type": "string", "description": "改了什么:人话,讲决策与取舍,不复述 diff"},
        "why": {"type": "string", "description": "为什么改:从会话提取的意图来源;无会话依据时注明推测"},
        "decisions": {"type": "array", "items": {"type": "string"},
                      "description": "关键技术决策,含被否决的备选(如有)"},
        "risks": {"type": "array", "items": {"type": "string"},
                  "description": "该变更可能引入的 1-2 条风险,供日后验证"},
        "open_loops": {"type": "array", "items": {"type": "string"},
                       "description": "未闭环的 TODO / 未确认事项"},
    },
    "required": ["what", "why", "decisions", "risks", "open_loops"],
    "additionalProperties": False,
}


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
