"""codetalk review —— 零-LLM 的 review 现场入口。

把工具从「手输 file:line 的事后考古」变「review/commit 现场粘 diff 即得」:解析统一 diff →
对每个改动块调既有 blame.collect_graded 恢复真实历史决策 + 溯源精度(行级/文件级/无据);
无叙事覆盖的块**显式标「无据」而非编造**(诚实暴露接地命中率上限,对抗 AI 反推噪声)。
终端和结构化输出共享同一审查卡契约。零 LLM、不出网、出口脱敏、解析失败降级绝不崩。
"""
import hashlib
import subprocess
from pathlib import Path

from .blame import collect_graded, segment_has_why
from .cache import Cache
from .config import CACHE_DB_PATH, redact_data, redact_secrets
from .review_diff import parse_unified_diff_hunks

# 逐块 blame 是 O(hunks)(每块一次 git log -L);大仓大 diff(实测某深历史仓 276 块约 33s)会过慢,
# 上限内接地、超出截断并指引单点 blame——防 review 在中大仓上拖死。
MAX_REVIEW_HUNKS = 60

_PRECISION = {"line": "行级精确",
              "file": "文件级降级(可能含本块外历史)",
              "none": "无行历史"}

# 接地强度三档徽标:每块前置、一眼可读,把「这条 why 的逐字溯源粒度」的诚实信号顶到眼前
# (护城河)。三档统一用「溯源粒度」措辞(行级/文件级/无),纯 provenance 轴——即便徽标
# 被单独拎出展示也读不成语义判断,**绝不**打对错/可信。R6 钉死:零-LLM 不判
# grounded/inferred/unsupported。
_BADGE = {"line": "[行级溯源]",
          "file": "[文件级溯源]",
          "none": "[无逐字溯源]"}


def _has_decision_evidence(segment):
    return bool(segment.get("authored_decisions")
                or segment.get("authored_rejected")
                or segment.get("evidence")
                or segment.get("test_refs")
                or segment.get("pr_refs"))


def _precision_label(precision, segs):
    """每块『溯源精度』标注:前置三档徽标 + 确定性准度细节(行级/文件级/无据)+ 有据/仅提交记录。
    **非**判断这条 why 对不对(语义需模型,零-LLM 不判)。"""
    base = _PRECISION.get(precision, precision)
    if any(_has_decision_evidence(s) for s in segs):
        detail = "有据(人工决策/可核验来源)"
    elif any(segment_has_why(s) for s in segs):
        detail = "仅生成解释(非证据)"
    elif segs:
        detail = "仅提交记录(无叙事/决策记录,可先 codetalk enrich 查看计划)"
    else:
        detail = "无历史记录"
    return f"{_BADGE.get(precision, _BADGE['none'])} 溯源精度:{base} · {detail}"


def parse_unified_diff(text):
    """统一 diff → [(file, start, end)] 每 hunk 一条(post-image 行范围)。
    跟 `+++ b/<file>` 定位文件,`@@ … +start,count @@` 取范围;无法解析/纯删除块跳过,绝不崩。"""
    return [(hunk["file"], hunk["start"], hunk["end"])
            for hunk in parse_unified_diff_hunks(text)]


def _git_diff(pp):
    """工作树相对 HEAD 的 diff(本地 git,不出网)→ (text, error)。"""
    try:
        out = subprocess.run(["git", "-C", str(pp), "diff", "HEAD"],
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"git diff 失败:{exc}"
    if out.returncode != 0:
        return None, f"git diff 失败:{out.stderr.strip()[:200]}"
    return out.stdout, None


def _valid_segments(segments):
    list_fields = ("decisions", "rejected", "authored_decisions",
                   "authored_rejected", "generated_decisions",
                   "generated_rejected", "evidence", "test_refs", "pr_refs")
    return [segment for segment in segments
            if isinstance(segment, dict)
            and isinstance(segment.get("why", ""), str)
            and all(isinstance(segment.get(field, []), list)
                    for field in list_fields)]


def _primary_segment(segments):
    """Prefer rejected paths, then authored context, with newer records first."""
    valid = _valid_segments(segments)
    if not valid:
        return None
    return min(enumerate(valid), key=lambda item: (
        0 if item[1].get("authored_rejected") else
        1 if item[1].get("authored_decisions") else
        2 if segment_has_why(item[1]) else 3,
        -item[0],
    ))[1]


def _card_id(file, start, end, segment):
    anchor = (segment or {}).get("sha", "no-history")
    rejected = "\n".join((segment or {}).get("authored_rejected") or [])
    raw = f"{file}:{start}:{end}:{anchor}:{rejected}"
    return "review-" + hashlib.sha256(raw.encode()).hexdigest()[:12]


def _evidence_record(segment):
    return {
        "sha": segment.get("sha", ""),
        "date": segment.get("date", ""),
        "subject": segment.get("subject", ""),
        "decision_notes": {
            "chosen": segment.get("authored_decisions") or [],
            "rejected": segment.get("authored_rejected") or [],
        },
        "sessions": segment.get("evidence") or [],
        "tests": segment.get("test_refs") or [],
        "pull_requests": segment.get("pr_refs") or [],
    }


def _card(file, start, end, segments, precision, diff=""):
    valid = _valid_segments(segments)
    primary = _primary_segment(valid)
    if segments and not valid:
        segments, precision = [], "none"
    else:
        segments = valid
    rejected = list((primary or {}).get("authored_rejected") or [])
    chosen = list((primary or {}).get("authored_decisions") or [])
    has_context = bool(primary and segment_has_why(primary))
    kind = ("potential_conflict" if rejected else
            "decision_context" if has_context else "no_evidence")
    evidence = None
    interpretation = None
    if primary:
        evidence = {
            "primary": _evidence_record(primary),
            "supporting": [_evidence_record(segment) for segment in segments
                           if segment is not primary],
        }
        generated_summary = (primary.get("why") or "").strip()
        generated_decisions = primary.get("generated_decisions") or []
        generated_rejected = primary.get("generated_rejected") or []
        if generated_summary or generated_decisions or generated_rejected:
            interpretation = {
                "label": "generated_interpretation",
                "authoritative": False,
                "summary": generated_summary,
                "decisions": generated_decisions,
                "rejected": generated_rejected,
            }
    span = f"{file}:{start}-{end}"
    reason = (f"Current diff hunk {span} has no recoverable Git history; "
              "semantic applicability cannot be evaluated."
              if precision == "none" else
              f"Current diff hunk {span} maps to Git history for its changed "
              "range; semantic applicability is not evaluated.")
    association = {
        "reason": reason,
        "semantic_match": "not_evaluated",
    }
    return redact_data({
        "id": _card_id(file, start, end, primary),
        "kind": kind,
        "change": {"file": file, "start": start, "end": end, "diff": diff},
        "association": association,
        "provenance": {
            "precision": precision,
            "label": _precision_label(precision, segments),
        },
        "evidence": evidence,
        "interpretation": interpretation,
        "judgment": {"status": "unresolved"} if rejected else None,
    })


def build_review_cards(project_path, diff_text=None):
    """Build the shared deterministic review-card contract."""
    pp = Path(project_path).resolve()
    if diff_text is None:
        diff_text, err = _git_diff(pp)
        if err:
            return None, err, None
    hunks = parse_unified_diff_hunks(diff_text)
    if not hunks:
        return [], None, {
            "total_hunks": 0, "analyzed_hunks": 0,
            "truncated": False, "max_hunks": MAX_REVIEW_HUNKS,
        }
    total_hunks = len(hunks)
    hunks = hunks[:MAX_REVIEW_HUNKS]
    cache = Cache(CACHE_DB_PATH)
    cards = []
    try:
        for hunk in hunks:
            file, start, end = hunk["file"], hunk["start"], hunk["end"]
            try:
                segs, precision = collect_graded(cache, pp, file, start, end)
                cards.append(_card(file, start, end, segs, precision, hunk["diff"]))
            except Exception:  # noqa: BLE001 - external data must degrade
                cards.append(_card(file, start, end, [], "none", hunk["diff"]))
    finally:
        cache.close()
    cards.sort(key=lambda card: (
        {"potential_conflict": 0, "decision_context": 1,
         "no_evidence": 2}[card["kind"]],
        {"line": 0, "file": 1, "none": 2}.get(
            card["provenance"]["precision"], 3),
    ))
    return cards, None, {
        "total_hunks": total_hunks,
        "analyzed_hunks": len(hunks),
        "truncated": total_hunks > MAX_REVIEW_HUNKS,
        "max_hunks": MAX_REVIEW_HUNKS,
    }


def _render_card(card):
    change = card["change"]
    span = f"{change['file']}:{change['start']}-{change['end']}"
    if card["kind"] == "potential_conflict":
        title = f"[{card['id']}] 潜在决策冲突 · {span}"
    elif card["kind"] == "decision_context":
        title = f"[{card['id']}] 决策上下文 · {span}"
    else:
        title = f"[{card['id']}] 未找到决策证据 · {span}"
    lines = [title]
    evidence_region = card.get("evidence") or {}
    evidence = evidence_region.get("primary") or {}
    notes = evidence.get("decision_notes") or {}
    for text in notes.get("rejected") or []:
        lines.append(f"  否决备选(曾放弃):{text}")
    for text in notes.get("chosen") or []:
        lines.append(f"  决策:{text}")
    interpretation = card.get("interpretation")
    if interpretation:
        if interpretation["summary"]:
            lines.append(f"  生成解释(非证据):{interpretation['summary']}")
        for text in interpretation["rejected"]:
            lines.append(f"  生成解释·否决路径(非证据):{text}")
        for text in interpretation["decisions"]:
            lines.append(f"  生成解释·决策(非证据):{text}")
    if evidence:
        lines.append(f"  来源:[{evidence['sha'][:7]}] {str(evidence['date'])[:10]} "
                     f"{evidence['subject']} · commit 触达")
    elif card["kind"] == "no_evidence":
        lines.append("  无据:零-LLM 无从溯源,可先 codetalk enrich 查看计划")
    lines.append("  " + card["provenance"]["label"])
    lines.append("  关联只来自 git 历史,未做语义判定;需要人工判断。")
    return "\n".join(lines)


def render_review_cards(cards, meta):
    if not cards:
        return "没有可分析的改动块(diff 为空或无法解析)。"
    conflicts = [card for card in cards if card["kind"] == "potential_conflict"]
    lines = ["# review 接地(零 LLM,决策证据 + 溯源精度)",
             "> CodeTalk 只恢复记录并说明关联;"
             "是否适用于当前改动由人判断。", ""]
    if conflicts:
        lines.extend(["## 拦截检查:改动触及曾否决的方案",
                      "> 确认结果可记录到 docs/discovery/interceptions.md。", ""])
    lines.append("\n\n".join(_render_card(card) for card in cards))
    if meta["truncated"]:
        lines.extend(["", f"> 注:diff 含 {meta['total_hunks']} 个改动块,"
                      f"只接地前 {meta['max_hunks']};其余请用 "
                      "`codetalk blame <文件:行>` 单点查。"])
    return redact_secrets("\n".join(lines))


def review(project_path, diff_text=None):
    """→ (report_text, error)。diff_text=None → 用 git diff HEAD。"""
    cards, err, meta = build_review_cards(project_path, diff_text)
    if err:
        return None, err
    return render_review_cards(cards, meta), None
