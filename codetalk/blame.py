"""blame:零-LLM 行级决策溯源 —— ask 的确定性孪生。

给定文件(可选行范围),用 git 行历史(line_log,行级失败降级文件级)找出触达这些
行的 commit,映射到已缓存叙事 + Vibe-Decision 面包屑,确定性打印每段决策史
(SHA·日期·subject·decisions)。ask 用 LLM 综合,blame 只如实罗列;无 key 也能用。
"""
import json
import sys
from pathlib import Path

from . import grounding_render as gr
from .cache import Cache
from .config import CACHE_DB_PATH, redact_data, redact_secrets
from .gitlog import (commit_body, commit_meta, file_log, line_log,
                     parse_breadcrumbs, parse_rejected, parse_target)

_parse_target = parse_target          # 与 ask 同口径,搬到 gitlog 共享


def segment_has_why(seg):
    """该段是否带 authored why(narrative why / decisions / 否决备选 / evidence 任一)。
    Vibe-Watch(risks)是前瞻预测、非『为什么这么写』,不计(与 grounding_hitrate/recall 同口径)。"""
    return bool((seg.get("why") or "").strip() or seg.get("decisions")
                or seg.get("rejected") or seg.get("evidence"))


def _resolve_shas(project_path, file, start, end):
    """→ (shas 旧→新, precision)。precision 是**确定性溯源准度**信号、非语义对错:
    line=行级精确命中;file=行级失败或无范围→文件级降级(可能含本块外历史);none=无任何历史。"""
    if start is not None:
        shas, err = line_log(project_path, file, start, end)
        if not err:
            return shas, ("line" if shas else "none")
        shas, _ = file_log(project_path, file)        # 行级失败 → 文件级降级
        return shas, ("file" if shas else "none")
    shas, _ = file_log(project_path, file)
    return shas, ("file" if shas else "none")


def _build_segments(cache, project_path, shas):
    """shas → 每 commit 一段(旧→新),含 sha/date/subject/why/decisions/risks/evidence/refs。
    每段 decisions = 缓存叙事决策 ∪ 面包屑(去重,缓存已折入不重复)。"""
    segments = []
    for sha in shas:
        narrative = cache.get_narrative(sha) or {}
        body = commit_body(project_path, sha)
        authored_decisions, authored_risks = parse_breadcrumbs(body)
        authored_rejected = parse_rejected(body)
        generated_decisions = narrative.get("decisions") or []
        generated_rejected = narrative.get("rejected") or []
        decs = list(dict.fromkeys(generated_decisions + authored_decisions))
        risks = list(dict.fromkeys(
            (narrative.get("risks") or []) + authored_risks))
        rejected = list(dict.fromkeys(generated_rejected + authored_rejected))
        date_iso, subject = commit_meta(project_path, sha)
        segments.append({
            "sha": sha, "date": date_iso, "subject": subject,
            "why": narrative.get("why") or "",
            "decisions": decs, "risks": risks, "rejected": rejected,
            "authored_decisions": authored_decisions,
            "authored_rejected": authored_rejected,
            "generated_decisions": [d for d in generated_decisions
                                    if d not in authored_decisions],
            "generated_rejected": [r for r in generated_rejected
                                   if r not in authored_rejected],
            "evidence": narrative.get("evidence") or [],  # 旧缓存无键 .get 兼容
            "test_refs": narrative.get("test_refs") or [],
            "pr_refs": narrative.get("pr_refs") or [],
        })
    return segments


def collect_segments(cache, project_path, file, start, end):
    """→ 触达这些行的每个 commit 一段(旧→新)。行级失败降级文件级。
    (契约不变:adr_export/review/retrieval/mcp_server/blame 五处依赖此签名与行为;
    需溯源准度信号时用 collect_graded。)"""
    shas, _ = _resolve_shas(project_path, file, start, end)
    return _build_segments(cache, project_path, shas)


def collect_graded(cache, project_path, file, start, end):
    """同 collect_segments,但额外返回溯源精度 → (segments, precision)。
    供 review 诚实标注每块『这块溯源有多准』(行级精确 / 文件级降级 / 无据),非判 why 对错。"""
    shas, precision = _resolve_shas(project_path, file, start, end)
    return _build_segments(cache, project_path, shas), precision


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
        for rej in seg.get("rejected") or []:        # 否决备选:diff 取不到的 why-NOT,防重引入
            lines.append(f"  否决备选(曾放弃):{rej}")
        for risk in seg["risks"]:
            lines.append(f"  待验证:{risk}")
        _emit_evidence(lines, seg.get("evidence") or [])
        _emit_test_refs(lines, seg.get("test_refs") or [])
        _emit_pr_refs(lines, seg.get("pr_refs") or [])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def blame(project_path, target, json_output=False):
    """CLI 入口:解析→收集→确定性打印,返回退出码。零 LLM,无 key 也能用。"""
    file, start, end = _parse_target(target)
    pp = Path(project_path).resolve()
    cache = Cache(CACHE_DB_PATH)
    segments = collect_segments(cache, pp, file, start, end)
    cache.close()
    if not segments:
        print(f"错误:{file} 没有可用的提交历史,无从溯源。", file=sys.stderr)
        return 2
    if json_output:
        # 脱敏在 json.dumps 之前(对原始字符串叶子):dumps 会把 " 转义,
        # 若先 dumps 后 redact,key="value" 形式 secret 会因引号转义漏网(见 redact_data 注释)
        print(json.dumps(redact_data(segments), ensure_ascii=False), end="")
    else:
        print(redact_secrets(_format(file, start, end, segments)), end="")
        # 冷启动 on-ramp:全是裸 subject(无 why/决策/面包屑)时,别让陌生人以为=git log。
        # 末行(stderr,不污染管道)指下一步:富集或装面包屑捕捉。
        if not any(segment_has_why(s) for s in segments):
            print("\n提示:该文件暂无决策记录(仅 commit 标题)。跑 `codetalk enrich .` "
                  "补叙事,或 `codetalk install-agent-seed .` 让 AI 提交时留 why。",
                  file=sys.stderr)
    return 0
