"""单代码 AI 提问:接项目记忆对一段代码作接地回答。

write-time 捕获(commit trailer 面包屑)+ read-time 廉价检索(git log -L → 已缓存
叙事 + 面包屑 → 一次轻 LLM)。无 key/失败时降级为打印该代码的原始决策史,绝不崩。
"""
import hashlib
import re
import sys
from pathlib import Path

from .cache import Cache
from .config import CACHE_DB_PATH, load_config, redact_secrets
from .gitlog import line_log, file_log, commit_body, parse_breadcrumbs
from .llm import ASK_SCHEMA, ASK_SYSTEM_PROMPT, LLMClient, LLMError

EXCERPT = 200
CONTEXT_BUDGET = 6000
_RANGE_RE = re.compile(r"^(\d+)(?:-(\d+))?$")


def _parse_target(target):
    """'foo.py' → ('foo.py', None, None);'foo.py:42-60' → ('foo.py', 42, 60);
    'foo.py:42' → ('foo.py', 42, 42)。冒号右侧不是行号则整串当文件(路径含冒号罕见)。"""
    if ":" in target:
        file, _, tail = target.rpartition(":")
        match = _RANGE_RE.match(tail)
        if file and match:
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else start
            return file, start, end
    return target, None, None


def _retrieve(project_path, file, start, end, cache):
    """→ (context_str, shas oldest-first, code_state)。无历史时 context_str 为 ''。
    code_state = 命中行最新 commit SHA,进缓存键 → 代码一变旧答案自然失效。"""
    if start is not None:
        shas, err = line_log(project_path, file, start, end)
        if err:                       # 行级失败 → 文件级降级
            shas, _ = file_log(project_path, file)
    else:
        shas, _ = file_log(project_path, file)
    blocks = []
    for sha in shas:
        narrative = cache.get_narrative(sha) or {}
        decisions, watches = parse_breadcrumbs(commit_body(project_path, sha))
        decs = (narrative.get("decisions") or []) + decisions
        risks = (narrative.get("risks") or []) + watches
        parts = [f"[{sha[:7]}]"]
        if narrative.get("why"):
            parts.append("意图:" + narrative["why"][:EXCERPT])
        if decs:
            parts.append("决策:" + ";".join(decs)[:EXCERPT])
        if risks:
            parts.append("风险/待验证:" + ";".join(risks)[:EXCERPT])
        blocks.append(" / ".join(parts))
    context = "\n".join(blocks)[:CONTEXT_BUDGET]
    code_state = shas[-1] if shas else ""
    return context, shas, code_state


def _ask_prompt(context, question):
    return ("材料(这段代码相关 commit 的叙事与决策面包屑,旧→新):\n"
            f"{context}\n\n问题:{question}\n"
            "只据材料回答;材料不足就说『材料不足』。")


def _format(payload):
    cited = "、".join(payload.get("cited_shas") or []) or "(无)"
    out = payload.get("answer", "")
    if payload.get("unsure"):
        out += f"\n\n[不确定] {payload['unsure']}"
    return f"{out}\n\n据此回答的 commit:{cited}"


def _write_note(vault_path, project, target, question, payload):
    vault = Path(vault_path).expanduser()
    vault.mkdir(parents=True, exist_ok=True)
    slug = hashlib.sha256(f"{target}|{question}".encode()).hexdigest()[:8]
    note = f"# 提问:{target}\n\n> {question}\n\n{_format(payload)}\n"
    (vault / f"{project}-ask-{slug}.md").write_text(
        redact_secrets(note), encoding="utf-8")


def answer_question(cache, llm, project_path, project, target, question,
                    vault_path=None):
    """核心:解析→检索→(命中缓存/无 key 降级/调 LLM)→脱敏缓存→(可选)写笔记。
    返回 (text, error_or_None)。llm=None 表示无 key,降级打印原始决策史。"""
    file, start, end = _parse_target(target)
    context, shas, code_state = _retrieve(project_path, file, start, end, cache)
    if not context:
        return None, f"{file} 没有可用的提交历史,无从回答。"
    key = "ask:" + hashlib.sha256(
        f"{file}|{start}-{end}|{question}|{code_state}".encode()
    ).hexdigest()[:40]
    cached = cache.get_narrative(key)
    if cached:
        return _format(cached), None
    if llm is None:                       # 无 API key:降级到原始决策史
        return "(未配置 LLM,以下为这段代码的原始决策史)\n" + context, None
    try:
        raw = llm.narrate(_ask_prompt(context, question),
                          schema=ASK_SCHEMA, system=ASK_SYSTEM_PROMPT)
    except LLMError:
        return "(LLM 调用失败,以下为原始决策史)\n" + context, None
    payload = {
        "answer": redact_secrets(str(raw.get("answer", ""))),
        "cited_shas": [str(s) for s in (raw.get("cited_shas") or [])],
        "unsure": redact_secrets(str(raw.get("unsure", ""))),
    }
    cache.put_narrative(key, project, llm.model, payload)
    if vault_path:
        _write_note(vault_path, project, target, question, payload)
    return _format(payload), None


def ask(project_path, target, question, vault=None):
    """CLI 入口:装配 cache/llm,转 answer_question,打印,返回退出码。"""
    cfg = load_config()
    if vault:
        cfg["vault_path"] = vault
    pp = Path(project_path).resolve()
    cache = Cache(CACHE_DB_PATH)
    try:
        llm = LLMClient(cfg)
    except LLMError:
        llm = None                        # 无 key → 降级,不报错退出
    text, err = answer_question(cache, llm, pp, pp.name, target, question,
                                cfg["vault_path"] if vault else None)
    cache.close()
    if err:
        print(f"错误:{err}", file=sys.stderr)
        return 2
    print(text)
    return 0
