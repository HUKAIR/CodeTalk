"""主题级内容召回(零-LLM,确定性接地):不带 file target,在整个仓里找『当初为什么』。

对位 N=2 问卷里用户反复 grep 跨文件找 why 的痛:ask/blame 都是 file-targeted,
本入口给 FTS 内容召回(cache.search_narratives)配真实消费者——返回真实 commit 的
why/决策/原话锚点,**不让 LLM 重述**(护城河:对抗 AI 反推式幻觉)。

collect_topic_hits 返回结构化命中(供 retrieval/web 既渲染成喂 LLM 的材料、又 id 化进
citations,同源不变式);topic_search 在其上做零-LLM 文本渲染。渲染复用 ask 的
确定性 evidence/test/pr 锚点格式器(同一套接地口径,不重写)。
"""
from . import conversation
from .ask import format_evidence, format_pr_refs, format_test_refs
from .config import redact_secrets
from .gitlog import merge_breadcrumbs

NO_HIT = ("没有在项目记忆里找到与该主题相关的 commit 叙事。\n"
          "可能:① 关键词太短(需 ≥3 字符)或过于生僻;② 这段历史还没被 digest 富集。\n"
          "试试换个关键词,或先跑 vibetrace digest 富集叙事。")


def collect_topic_hits(cache, project_path, question):
    """主题级零-LLM 检索 → 结构化命中 list[dict]。解析真实 commit 命中(get_narrative +
    merge_breadcrumbs)与对话命中(conv: → web_conversations);叙事缺失/非 git 仓容错降级。"""
    hits = []
    for key in cache.search_narratives(question):
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
    """主题级零-LLM 召回入口:collect_topic_hits → 每命中确定性渲染。无命中→友好提示。
    返回纯文本;出口统一脱敏(header 回显原 question,与 MCP 出口同口径)。"""
    hits = collect_topic_hits(cache, project_path, question)
    if not hits:
        return NO_HIT
    header = f"# 主题召回:{question}(命中 {len(hits)} 条,按相关度,零 LLM)\n"
    return redact_secrets(header + "\n\n".join(render_hit(h) for h in hits))
