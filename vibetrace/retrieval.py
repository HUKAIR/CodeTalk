"""零-LLM 证据集装配(接地对话的护城河核心)。

C-3 不变式:**喂模型的材料 ≡ 面板展示的证据 ≡ 同源可核验记录**。
assemble 把检索到的真实记录(主题召回 ∪ file-target 行级溯源)装成「同一份」结构化命中,
既渲染成喂 LLM 的材料文本(含 evidence/test/pr 全文锚点,LLM 真读到原话),
又 id 化进 citations(面板用)。纯检索、零 LLM。
"""
from . import search
from .blame import collect_segments
from .gitlog import parse_target


def _seg_to_hit(seg):
    return {"sha": seg["sha"], "kind": "commit", "text": "",
            "why": seg.get("why") or "", "decisions": seg.get("decisions") or [],
            "evidence": seg.get("evidence") or [], "test_refs": seg.get("test_refs") or [],
            "pr_refs": seg.get("pr_refs") or []}


def _sources(hit):
    """结构化可跳转来源(供前端 hover 预览 / 点击跳真源):commit sha + PR(number/url/title)。
    conversation 仅作标识、无可跳 url——会话非稳定可寻址源,**不伪造跳转**(同 prompts 反幻觉纪律)。"""
    if hit["kind"] == "conversation":
        return [{"type": "session", "id": hit["sha"]}]
    src = [{"type": "commit", "sha": hit["sha"][:12]}]
    for pr in hit.get("pr_refs") or []:
        if pr.get("url"):
            src.append({"type": "pr", "number": pr.get("number"),
                        "url": pr["url"], "title": pr.get("title", "")})
    return src


def _citation(idx, hit):
    # evidence = 该命中的确定性渲染(意图/决策/原话/测试/PR),供前端点开就地核验:
    # 与喂模型的材料同源(C-3),随响应回前端,点开无需再请求后端。
    # sources = 结构化锚点,供 hover 预览 + 点击跳真实 commit/PR(GitLens hover-card 范式)。
    return {"id": idx, "sha": hit["sha"][:12], "kind": hit["kind"],
            "evidence": search.render_hit(hit), "sources": _sources(hit)}


def assemble(cache, project_path, question, target=None):
    """→ {hits, material, citations}(同源)。target 给定(file 或 file:起-止)时叠加行级溯源。
    任何检索失败容错降级,绝不崩。"""
    hits = list(search.collect_topic_hits(cache, project_path, question))
    if target:
        try:
            file, start, end = parse_target(target)
            for seg in collect_segments(cache, project_path, file, start, end):
                hits.append(_seg_to_hit(seg))
        except Exception:                       # noqa: BLE001 目标解析/git 失败 → 退回主题命中
            pass
    seen, uniq = set(), []
    for h in hits:                              # 按 sha 去重(主题与行级可能命中同一 commit)
        if h["sha"] in seen:
            continue
        seen.add(h["sha"])
        uniq.append(h)
    material = "\n\n".join(search.render_hit(h) for h in uniq)   # 同一份 → 喂 LLM 的材料
    citations = [_citation(i, h) for i, h in enumerate(uniq)]    # 同一份 → 面板 id 化
    return {"hits": uniq, "material": material, "citations": citations}
