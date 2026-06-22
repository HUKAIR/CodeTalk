"""主题级内容召回(零-LLM,确定性接地):不带 file target,在整个仓里找『当初为什么』。

对位 N=2 问卷里用户反复 grep 跨文件找 why 的痛:ask/blame 都是 file-targeted,
本入口给 FTS 内容召回(cache.search_narratives)配真实消费者——返回真实 commit 的
why/决策/原话锚点,**不让 LLM 重述**(护城河:对抗 AI 反推式幻觉)。

渲染复用 ask 的确定性 evidence/test/pr 锚点格式器(同一套接地口径,不重写)。
"""
from .ask import format_evidence, format_pr_refs, format_test_refs
from .config import redact_secrets
from .gitlog import merge_breadcrumbs

NO_HIT = ("没有在项目记忆里找到与该主题相关的 commit 叙事。\n"
          "可能:① 关键词太短(需 ≥3 字符)或过于生僻;② 这段历史还没被 digest 富集。\n"
          "试试换个关键词,或先跑 vibetrace digest 富集叙事。")


def _format_hit(cache, project_path, sha):
    """单个命中 → 确定性文本块:sha 短码 + why + 决策 + 原话/测试/PR 锚点。
    叙事缺失/无 git 上下文均容错降级,绝不崩。"""
    narrative = cache.get_narrative(sha) or {}
    try:                                  # 决策 = 叙事决策 ∪ commit 面包屑(去重)
        decs, _risks = merge_breadcrumbs(narrative, project_path, sha)
    except Exception:                     # 非 git 仓 / 派生键 → 退回纯叙事决策
        decs = narrative.get("decisions") or []
    lines = [f"[{sha[:7]}]"]
    if narrative.get("why"):
        lines.append(f"  意图:{narrative['why']}")
    for dec in decs:
        lines.append(f"  决策:{dec}")
    for block in (format_evidence(narrative.get("evidence") or []),
                  format_test_refs(narrative.get("test_refs") or []),
                  format_pr_refs(narrative.get("pr_refs") or [])):
        if block:                         # 锚点块缩进进该 commit 段
            lines.append("  " + block.replace("\n", "\n  "))
    return "\n".join(lines)


def topic_search(cache, project_path, question):
    """主题级零-LLM 召回入口:search_narratives(question) → 每个命中确定性格式化。
    无命中 → 友好提示。返回纯文本(脱敏在 put_narrative 落盘时已做,内容来自已脱敏叙事)。"""
    shas = cache.search_narratives(question)
    if not shas:
        return NO_HIT
    header = f"# 主题召回:{question}(命中 {len(shas)} 条,按相关度,零 LLM)\n"
    body = header + "\n\n".join(
        _format_hit(cache, project_path, sha) for sha in shas)
    return redact_secrets(body)  # header 回显原 question,出口统一脱敏(与 MCP 出口同口径)
