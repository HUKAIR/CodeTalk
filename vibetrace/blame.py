"""blame:零-LLM 行级决策溯源 —— ask 的确定性孪生。

给定文件(可选行范围),用 git 行历史(line_log,行级失败降级文件级)找出触达这些
行的 commit,映射到已缓存叙事 + Vibe-Decision 面包屑,确定性打印每段决策史
(SHA·日期·subject·decisions)。ask 用 LLM 综合,blame 只如实罗列;无 key 也能用。
"""
import sys
from pathlib import Path

from . import grounding_render as gr
from .cache import Cache
from .config import CACHE_DB_PATH
from .gitlog import commit_meta, file_log, line_log, merge_breadcrumbs, parse_target

_parse_target = parse_target          # 与 ask 同口径,搬到 gitlog 共享


def collect_segments(cache, project_path, file, start, end):
    """→ 触达这些行的每个 commit 一段(旧→新),含 sha/date/subject/decisions/risks。
    行级失败降级文件级;每段 decisions = 缓存叙事决策 ∪ 面包屑(去重,缓存已折入不重复)。"""
    if start is not None:
        shas, err = line_log(project_path, file, start, end)
        if err:                            # 行级失败 → 文件级降级
            shas, _ = file_log(project_path, file)
    else:
        shas, _ = file_log(project_path, file)
    segments = []
    for sha in shas:
        narrative = cache.get_narrative(sha) or {}
        decs, risks = merge_breadcrumbs(narrative, project_path, sha)
        date_iso, subject = commit_meta(project_path, sha)
        segments.append({
            "sha": sha, "date": date_iso, "subject": subject,
            "why": narrative.get("why") or "",
            "decisions": decs, "risks": risks,
            "evidence": narrative.get("evidence") or [],  # 旧缓存无键 .get 兼容
            "test_refs": narrative.get("test_refs") or [],
            "pr_refs": narrative.get("pr_refs") or [],
        })
    return segments


def _emit_evidence(lines, evidence):
    """把该段原话锚点确定性追加进输出(零 LLM):source·短id·ts + 原话/AI 片段;
    支撑全为 low 时加置信度警示。无 evidence 不输出块。脱敏已在 enrich 上游做。"""
    if not evidence:
        return
    lines.append("  " + gr.EVIDENCE_TITLE)
    for ev in evidence:
        sid = (ev.get("session_id") or "")[:7]
        lines.append(f"    [{ev.get('source', '?')}·{sid}·{ev.get('ts', '')}"
                     f"·{ev.get('confidence', '?')}]")
        for p in ev.get("prompts") or []:
            lines.append(f"      原话:{p}")
        for e in ev.get("excerpts") or []:
            lines.append(f"      AI:{e}")
    if gr.evidence_low_confidence(evidence):
        lines.append("    " + gr.EVIDENCE_LOW_WARN)


def _emit_test_refs(lines, test_refs):
    """「相关测试(从测试场景反推设计)」确定性追加(零 LLM)。无则不输出。"""
    if not test_refs:
        return
    lines.append("  " + gr.TEST_REFS_TITLE)
    for tr in test_refs:
        names = "、".join(tr.get("names") or []) or "(无显式 test_ 用例)"
        lines.append(f"    {tr.get('path', '')} — {names}")


def _emit_pr_refs(lines, pr_refs):
    """「相关 PR 讨论(当初的需求背景)」确定性追加(零 LLM)。无则不输出。"""
    if not pr_refs:
        return
    lines.append("  " + gr.PR_REFS_TITLE)
    for pr in pr_refs:
        lines.append(f"    #{pr.get('number')} {pr.get('title', '')} — "
                     f"{pr.get('snippet', '')}")


def _format(file, start, end, segments):
    span = f"{file}:{start}-{end}" if start is not None else file
    lines = [f"# blame {span}(旧→新,共 {len(segments)} 个 commit 触达)\n"]
    for seg in segments:
        date = (seg["date"] or "")[:10]    # 仅日期部分
        lines.append(f"[{seg['sha'][:7]}] {date} {seg['subject']}")
        if seg["why"]:
            lines.append(f"  意图:{seg['why']}")
        for dec in seg["decisions"]:
            lines.append(f"  决策:{dec}")
        for risk in seg["risks"]:
            lines.append(f"  待验证:{risk}")
        _emit_evidence(lines, seg.get("evidence") or [])
        _emit_test_refs(lines, seg.get("test_refs") or [])
        _emit_pr_refs(lines, seg.get("pr_refs") or [])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def blame(project_path, target):
    """CLI 入口:解析→收集→确定性打印,返回退出码。零 LLM,无 key 也能用。"""
    file, start, end = _parse_target(target)
    pp = Path(project_path).resolve()
    cache = Cache(CACHE_DB_PATH)
    segments = collect_segments(cache, pp, file, start, end)
    cache.close()
    if not segments:
        print(f"错误:{file} 没有可用的提交历史,无从溯源。", file=sys.stderr)
        return 2
    print(_format(file, start, end, segments), end="")
    return 0
