"""主题级内容召回(零-LLM,确定性接地):不带 file target,在整个仓里找『当初为什么』。

对位 N=2 问卷里用户反复 grep 跨文件找 why 的痛:ask/blame 都是 file-targeted,
本入口给 FTS 内容召回(cache.search_narratives)配真实消费者——返回真实 commit 的
why/决策/原话锚点,**不让 LLM 重述**(护城河:对抗 AI 反推式幻觉)。

collect_topic_hits 返回结构化命中(供 retrieval/web 既渲染成喂 LLM 的材料、又 id 化进
citations,同源不变式);topic_search 在其上做零-LLM 文本渲染。渲染复用 ask 的
确定性 evidence/test/pr 锚点格式器(同一套接地口径,不重写)。
"""
import re

from . import conversation
from .ask import format_evidence, format_pr_refs, format_test_refs
from .config import redact_secrets
from .gitlog import (collect_commit_files, merge_breadcrumbs,
                     parse_breadcrumbs, parse_rejected)

_CJK = re.compile(r"[一-鿿]")


def split_terms(question):
    """关键词切分 + 阈值:含 CJK 的词最低 2 字符,纯 ASCII 维持 3。→ 小写 term 列表。"""
    return [t.lower() for t in (question or "").split()
            if len(t) >= (2 if _CJK.search(t) else 3)]


def collect_breadcrumb_hits(project_path, question):
    """零-LLM 逐字检索:关键词命中在 Vibe-Decision/Watch/Rejected 行内 → tier
    "breadcrumb";只命中在 subject/body 其他位置 → tier "text"(摘录命中行)。同一
    commit 只按最高级列一次。大小写不敏感子串匹配,不读 LLM 富集缓存。
    → (hits:面包屑在前、各级内新→旧, 带任一 Vibe-* 记录的 commit 数);
    非 git 仓/无有效 term 容错降级。"""
    terms = split_terms(question)
    commits, err = collect_commit_files(project_path)
    if err:
        return [], 0
    noted, bc_hits, text_hits = 0, [], []
    for c in commits:
        decs, watches = parse_breadcrumbs(c["body"])
        lines = ([("Vibe-Decision", t) for t in decs]
                 + [("Vibe-Watch", t) for t in watches]
                 + [("Vibe-Rejected", t) for t in parse_rejected(c["body"])])
        if lines:
            noted += 1
        hit = {"sha": c["sha"], "date": c["date"].date().isoformat(),
               "subject": c["subject"]}
        matched = [(kind, text) for kind, text in lines
                   if any(term in text.lower() for term in terms)]
        if matched:
            bc_hits.append({**hit, "tier": "breadcrumb", "lines": matched})
            continue                                # 最高级命中,不再列提交原文级
        excerpt = next((ln.strip() for ln in [c["subject"], *c["body"].splitlines()]
                        if terms and any(t in ln.lower() for t in terms)), None)
        if excerpt is not None:
            text_hits.append({**hit, "tier": "text", "lines": [("摘录", excerpt)]})
    bc_hits.reverse(); text_hits.reverse()          # collect 旧→新;各级内新在前
    return bc_hits + text_hits, noted


def render_breadcrumb_hit(hit):
    """单个 git 逐字命中 → 确定性文本块:分级源标注 + SHA 短码 + 日期 + 主题 +
    原样 Vibe-* 行(面包屑级)或命中行摘录(提交原文级)。"""
    label = "[面包屑·逐字]" if hit["tier"] == "breadcrumb" else "[提交原文·逐字]"
    lines = [f"{label} [{hit['sha'][:7]}] {hit['date']} {hit['subject']}"]
    lines += [f"  {kind}: {text}" for kind, text in hit["lines"]]
    return "\n".join(lines)


def _no_hit(noted):
    """空态分因指路:仓里根本没有 Vibe-* 记录 → 指 install-agent-seed/demo;
    有记录但全部 commit message 都没命中 → 建议换词(并说明阈值)。"""
    if noted:
        return (f"没有命中:全部 commit message(含 {noted} 个带 Vibe-* 决策记录的)"
                "都不含本次关键词,叙事缓存也没有相关内容。\n"
                "试试换个关键词(子串匹配;含中文的词 ≥2 字符,纯英文 ≥3)。")
    return ("没有命中:这个仓库还没有任何 Vibe-* 决策记录,叙事缓存也没有相关内容。\n"
            "先跑 codetalk install-agent-seed 让后续提交自动留决策记录,"
            "或 codetalk demo 30 秒看有记录时的真实效果。")


def collect_topic_hits(cache, project_path, question):
    """主题级零-LLM 检索 → 结构化命中 list[dict]。解析真实 commit 命中(get_narrative +
    merge_breadcrumbs)与对话命中(conv: → web_conversations);叙事缺失/非 git 仓容错降级。"""
    hits = []
    pkey = str(project_path)        # 与 commit_narratives.project 同口径(调用方已 resolve),按项目隔离
    for key in cache.search_narratives(question, pkey):
        if conversation.is_conv_key(key):           # 反哺:落库的讨论也是接地源
            turn = conversation.get_turn(cache, conversation.turn_id_of(key))
            if turn:
                hits.append({"sha": key, "kind": "conversation", "text": turn["text"],
                             "why": "", "decisions": [], "rejected": [], "evidence": [],
                             "test_refs": [], "pr_refs": []})
            continue
        narrative = cache.get_narrative(key) or {}
        try:                                        # 决策/否决备选 = 叙事 ∪ commit 面包屑(去重)
            decs, _risks, rej = merge_breadcrumbs(narrative, project_path, key)
        except Exception:                           # noqa: BLE001 非 git/派生键 → 纯叙事
            decs = narrative.get("decisions") or []
            rej = narrative.get("rejected") or []
        hits.append({"sha": key, "kind": "commit", "text": "",
                     "why": narrative.get("why") or "", "decisions": decs,
                     "rejected": rej,
                     "evidence": narrative.get("evidence") or [],
                     "test_refs": narrative.get("test_refs") or [],
                     "pr_refs": narrative.get("pr_refs") or []})
    return hits


def render_hit(hit):
    """单个结构化命中 → 确定性文本块(零 LLM):sha 短码 + why + 决策 + 原话/测试/PR 锚点。
    对话命中渲染成「[你的讨论] text」。供 topic_search 与 retrieval 的材料文本共用。"""
    if hit["kind"] == "conversation":
        return f"[你的讨论] {hit['text']}"
    lines = [f"[{hit['sha'][:7]}]"]
    if hit["why"]:
        lines.append(f"  意图:{hit['why']}")
    for dec in hit["decisions"]:
        lines.append(f"  决策:{dec}")
    for rej in hit.get("rejected") or []:
        lines.append(f"  否决备选(曾放弃):{rej}")
    for block in (format_evidence(hit["evidence"]), format_test_refs(hit["test_refs"]),
                  format_pr_refs(hit["pr_refs"])):
        if block:                                   # 锚点块缩进进该 commit 段
            lines.append("  " + block.replace("\n", "\n  "))
    return "\n".join(lines)


def topic_search(cache, project_path, question):
    """主题级零-LLM 召回入口:逐字面包屑检索 ∪ 富集/对话召回,分源标注合并输出。
    无命中→分因指路。返回纯文本;出口统一脱敏(header 回显原 question,与 MCP 同口径)。"""
    bc_hits, noted = collect_breadcrumb_hits(project_path, question)
    hits = collect_topic_hits(cache, project_path, question)
    if not bc_hits and not hits:
        return _no_hit(noted)
    header = (f"# 主题召回:{question}(命中 {len(bc_hits) + len(hits)} 条,零 LLM;"
              "固定排序:面包屑逐字 → 提交原文逐字 → 叙事)\n")
    blocks = [render_breadcrumb_hit(h) for h in bc_hits]
    blocks += [render_hit(h) if h["kind"] == "conversation"
               else "[叙事·LLM生成] " + render_hit(h) for h in hits]
    return redact_secrets(header + "\n\n".join(blocks))
