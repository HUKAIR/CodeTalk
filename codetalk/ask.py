"""单代码 AI 提问:接项目记忆对一段代码作接地回答。

write-time 捕获(commit trailer 面包屑)+ read-time 廉价检索(git log -L → 已缓存
叙事 + 面包屑 → 一次轻 LLM)。无 key/失败时降级为打印该代码的原始决策史,绝不崩。
"""
import hashlib
import json
import sys
from pathlib import Path

from . import grounding_render as gr
from .cache import Cache
from .config import CACHE_DB_PATH, load_config, redact_data, redact_secrets
from .gitlog import (line_log, file_log, merge_breadcrumbs, parse_target,
                     commit_meta)
from .llm import LLMClient, LLMError
from .prompts import ASK_SCHEMA, ASK_SYSTEM_PROMPT

EXCERPT = 200
CONTEXT_BUDGET = 6000
_parse_target = parse_target          # 与 blame 同口径,搬到 gitlog 共享


def _since_args(since):
    """把 --since 的值分类成 git log 的范围 token(确定性检索,不引向量库):
    含 '..' → 当 commit 范围(如 abc..def)直接作 rev arg;否则当日期 → --since=<值>。
    None/空 → 无范围([]),退化为全历史检索。"""
    since = (since or "").strip()
    if not since:
        return []
    if ".." in since:
        return [since]
    return [f"--since={since}"]


def _retrieve(project_path, file, start, end, cache, since=None):
    """→ (context_str, shas oldest-first, code_state, evidence, test_refs, pr_refs)。
    无历史时 context_str 为 ''。code_state = 命中行最新 commit SHA,进缓存键 →
    代码一变旧答案自然失效。evidence = 命中 SHA narrative 的原话锚点汇总;
    pr_refs = 命中 narrative 的 PR 讨论汇总(按 number 去重);旧缓存无键 .get 兼容。
    since:把检索从空间(文件:行)再叠一层时间范围(日期/commit 范围),确定性过滤。"""
    extra = _since_args(since)
    if start is not None:
        shas, err = line_log(project_path, file, start, end, extra=extra)
        if err:                       # 行级失败 → 文件级降级
            shas, _ = file_log(project_path, file, extra=extra)
    else:
        shas, _ = file_log(project_path, file, extra=extra)
    blocks, evidence, test_refs, pr_refs = [], [], [], []
    _seen_ev, _seen_test, _seen_pr = set(), set(), set()
    for sha in shas:
        narrative = cache.get_narrative(sha) or {}
        decs, risks, rejected = merge_breadcrumbs(narrative, project_path, sha)
        for ev in narrative.get("evidence") or []:    # 原话锚点,按 (session_id, ts) 去重
            key_ev = (sid, ev.get("ts")) if (sid := ev.get("session_id")) else str(ev)
            if key_ev not in _seen_ev:
                _seen_ev.add(key_ev)
                evidence.append(ev)
        for tr in narrative.get("test_refs") or []:   # 本地测试接地源,按 path 去重
            if tr.get("path") not in _seen_test:
                _seen_test.add(tr.get("path"))
                test_refs.append(tr)
        for pr in narrative.get("pr_refs") or []:     # PR 讨论接地源,按 number 去重
            if pr.get("number") not in _seen_pr:
                _seen_pr.add(pr.get("number"))
                pr_refs.append(pr)
        # subject 兜底:无叙事无面包屑时也不只剩光秃 [sha](对齐 blame,冷启动可读)
        _date, subject = commit_meta(project_path, sha)
        parts = [f"[{sha[:7]}]" + (f" {subject}" if subject else "")]
        if narrative.get("why"):
            parts.append("意图:" + narrative["why"][:EXCERPT])
        if decs:
            parts.append("决策:" + ";".join(decs)[:EXCERPT])
        if rejected:
            parts.append("否决备选:" + ";".join(rejected)[:EXCERPT])
        if risks:
            parts.append("风险/待验证:" + ";".join(risks)[:EXCERPT])
        blocks.append(" / ".join(parts))
    # 单点脱敏在原始拼接文本上(非 JSON/LLM 编码后):context 由 commit body 面包屑直接拼成,
    # 未经 cache 脱敏。一处脱敏堵三个出口——MCP JSON(_json_text dumps 前)、CLI 降级 stdout、
    # 送外部 LLM 的 prompt(_ask_prompt→narrate,唯一出网例外也须先脱敏)。
    context = redact_secrets("\n".join(blocks)[:CONTEXT_BUDGET])
    code_state = shas[-1] if shas else ""
    return context, shas, code_state, evidence, test_refs, pr_refs


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


def format_evidence(evidence):
    """把原话锚点渲染成「原话佐证(可自行核验)」块,供 LLM 答案旁对照(对抗反推式编造)。
    每条列 source·session 短id·ts + 原话/AI 陈述片段;支撑全为 low 时加置信度警示。
    无 evidence → 返回 ''(调用方不追加该块,旧缓存无键经上游 .get 兼容)。脱敏在上游已做。"""
    if not evidence:
        return ""
    lines = [gr.EVIDENCE_TITLE]
    for ev in evidence:
        sid = (ev.get("session_id") or "")[:7]
        head = f"- [{ev.get('source', '?')}·{sid}·{ev.get('ts', '')}" \
               f"·{ev.get('confidence', '?')}]"
        lines.append(head)
        for p in ev.get("prompts") or []:
            lines.append(f"  原话:{p}")
        for e in ev.get("excerpts") or []:
            lines.append(f"  AI:{e}")
    if gr.evidence_low_confidence(evidence):
        lines.append(gr.EVIDENCE_LOW_WARN)
    return "\n".join(lines)


def format_test_refs(test_refs):
    """「相关测试(从测试场景反推设计)」块:列相关测试文件 + 用例名,供用户反推设计。
    无 → ''(调用方不追加)。对位用户1「看测试用例反推设计」(问卷一 Q3)。"""
    if not test_refs:
        return ""
    lines = [gr.TEST_REFS_TITLE]
    for tr in test_refs:
        names = "、".join(tr.get("names") or []) or "(无显式 test_ 用例)"
        lines.append(f"- {tr.get('path', '')} — {names}")
    return "\n".join(lines)


def format_pr_refs(pr_refs):
    """「相关 PR 讨论(当初的需求背景)」块:列 #N title — snippet,供反推需求背景。
    无 → ''(调用方不追加)。对位用户1「看 PR 描述找需求背景」(问卷一 Q3,最强 why 源)。"""
    if not pr_refs:
        return ""
    lines = [gr.PR_REFS_TITLE]
    for pr in pr_refs:
        lines.append(f"- #{pr.get('number')} {pr.get('title', '')} — "
                     f"{pr.get('snippet', '')}")
    return "\n".join(lines)


def _with_evidence(text, evidence, test_refs=(), pr_refs=()):
    for block in (format_evidence(evidence), format_test_refs(test_refs),
                  format_pr_refs(pr_refs)):
        if block:
            text = f"{text}\n\n{block}"
    return text


def _json_text(mode, target, question, shas, payload=None, context=None):
    """组装 agent 可读的结构化结果(与 agent-seed 写时捕获配成读写闭环)。
    llm/cache:带 LLM payload(answer/cited_shas/unsure);degraded:无 LLM,
    给出确定性检索结果(context 原始决策史 + shas),降级也不崩。
    context 已在 _retrieve 脱敏;此处再 redact_data 兜底(结构叶子,dumps 前)防遗漏出口。"""
    obj = {"mode": mode, "target": target, "question": question,
           "shas": list(shas or [])}
    if payload is not None:
        obj["answer"] = payload.get("answer", "")
        obj["cited_shas"] = list(payload.get("cited_shas") or [])
        obj["unsure"] = payload.get("unsure", "")
    if context is not None:
        obj["context"] = context
    return json.dumps(redact_data(obj), ensure_ascii=False, indent=2)


def _write_note(vault_path, project, target, question, payload):
    vault = Path(vault_path).expanduser()
    vault.mkdir(parents=True, exist_ok=True)
    slug = hashlib.sha256(f"{target}|{question}".encode()).hexdigest()[:8]
    note = f"# 提问:{target}\n\n> {question}\n\n{_format(payload)}\n"
    (vault / f"{project}-ask-{slug}.md").write_text(
        redact_secrets(note), encoding="utf-8")


def answer_question(cache, llm, project_path, project, target, question,
                    vault_path=None, since=None, as_json=False):
    """核心:解析→检索→(命中缓存/无 key 降级/调 LLM)→脱敏缓存→(可选)写笔记。
    返回 (text, error_or_None)。llm=None 表示无 key,降级打印原始决策史。
    since:把检索叠一层时间范围;as_json:text 改为 agent 可读的结构化 JSON。"""
    question = redact_secrets(question)   # 用户原始输入:在所有出口(json/note/prompt)前单点脱敏
    file, start, end = _parse_target(target)
    context, shas, code_state, evidence, test_refs, pr_refs = _retrieve(
        project_path, file, start, end, cache, since=since)
    if not context:
        return None, f"{file} 没有可用的提交历史,无从回答。"
    key = "ask:" + hashlib.sha256(
        f"{file}|{start}-{end}|{question}|{code_state}|{since or ''}".encode()
    ).hexdigest()[:40]
    cached = cache.get_narrative(key)
    if cached:
        _log_usage(project_path, "cache", llm)
        if as_json:
            return _json_text("cache", target, question, shas,
                              payload=cached), None
        return _with_evidence(_format(cached), evidence, test_refs, pr_refs), None
    if llm is None:                       # 无 API key:降级到原始决策史
        _log_usage(project_path, "degraded", llm)
        if as_json:
            return _json_text("degraded", target, question, shas,
                              context=context), None
        return _with_evidence(
            "(未配置 LLM,以下为这段代码的原始决策史)\n" + context,
            evidence, test_refs, pr_refs), None
    try:
        raw = llm.narrate(_ask_prompt(context, question),
                          schema=ASK_SCHEMA, system=ASK_SYSTEM_PROMPT)
    except LLMError:
        _log_usage(project_path, "degraded", llm)
        if as_json:
            return _json_text("degraded", target, question, shas,
                              context=context), None
        return _with_evidence(
            "(LLM 调用失败,以下为原始决策史)\n" + context,
            evidence, test_refs, pr_refs), None
    payload = {
        "answer": redact_secrets(str(raw.get("answer", ""))),
        "cited_shas": [str(s) for s in (raw.get("cited_shas") or [])],
        "unsure": redact_secrets(str(raw.get("unsure", ""))),
    }
    cache.put_narrative(key, project, llm.model, payload)
    _log_usage(project_path, "llm", llm)
    if vault_path:
        _write_note(vault_path, project, target, question, payload)
    if as_json:
        return _json_text("llm", target, question, shas, payload=payload), None
    return _with_evidence(_format(payload), evidence, test_refs, pr_refs), None


def _log_usage(project_path, mode, llm):
    """记一行 ask 用量(mode=cache/degraded/llm;带 LLM token 省额)。写失败不影响主流程。"""
    from . import report
    stats = getattr(llm, "stats", {}) if llm else {}
    report.append_usage({
        "command": "ask", "project": str(project_path), "mode": mode,
        "llm_calls": stats.get("calls", 0),
        "tokens_in": stats.get("input_tokens", 0),
        "tokens_out": stats.get("output_tokens", 0),
        "cache_hit_tokens": stats.get("cache_hit_tokens", 0),
    })


def ask(project_path, target, question, vault=None, since=None, as_json=False,
        no_llm=False):
    """CLI 入口:装配 cache/llm,转 answer_question,打印,返回退出码。"""
    cfg = load_config()
    if vault:
        cfg["vault_path"] = vault
    if no_llm:
        cfg["no_llm"] = True              # 硬关 LLM → 下方 LLMClient 抛 LLMError → 降级确定性
    pp = Path(project_path).resolve()
    cache = Cache(CACHE_DB_PATH)
    try:
        llm = LLMClient(cfg)
    except LLMError:
        llm = None                        # 无 key → 降级,不报错退出
    text, err = answer_question(cache, llm, pp, pp.name, target, question,
                                cfg["vault_path"] if vault else None,
                                since=since, as_json=as_json)
    cache.close()
    if err:
        print(f"错误:{err}", file=sys.stderr)
        return 2
    print(text)
    return 0
