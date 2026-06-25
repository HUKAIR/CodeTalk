"""ADR 导出(零 LLM):把一段代码的真实决策史确定性渲染成 MADR / Nygard 架构决策记录。

区别于手写 ADR 生态(adr-tools / Log4brains / pyadr 全手写、无一从 git 自动挖):vibetrace 从
真实 commit/决策**自动**导出,「来源」段附真实 commit SHA + 逐字原话(可核验,非 LLM 反推)——
「别人要你手写 ADR,vibetrace 从真实记录自动导出且逐字接地」。复用 blame.collect_segments;
纯字符串拼接、零 LLM、不触网、出口脱敏、绝不崩。
"""
import sys
from pathlib import Path

from .config import redact_secrets

FORMATS = ("madr", "nygard")


def _bullets(items):
    uniq = [str(x) for x in dict.fromkeys(items) if str(x).strip()]
    return ["- " + x for x in uniq] or ["-(未记)"]


def to_adr(target, segments, fmt="madr"):
    """segments(旧→新,blame.collect_segments 输出)→ 一份 markdown ADR。零 LLM、落地前脱敏。"""
    whys = [s["why"] for s in segments if s.get("why")]
    decisions = [d for s in segments for d in (s.get("decisions") or [])]
    risks = [r for s in segments for r in (s.get("risks") or [])]
    title = (segments[-1].get("subject") if segments else "") or target
    context = whys or ["(无叙事;先跑 vibetrace digest / enrich 富集)"]
    if fmt == "nygard":
        body = ["# " + title, "", "## Status", "accepted", "",
                "## Context", *context, "",
                "## Decision", *_bullets(decisions), "",
                "## Consequences", *_bullets(risks)]
    else:                                         # MADR(默认)
        body = ["# " + title, "", "- Status: accepted", "",
                "## Context and Problem Statement", *context, "",
                "## Decision Outcome", *_bullets(decisions), "",
                "## Consequences", *_bullets(risks)]
    body += ["", "## 来源(真实 commit,逐字可核验)", f"_目标:{target}_"]
    for s in segments:                            # 每个 commit 的 SHA + 逐字决策原话锚点
        body.append(f"- [{s['sha'][:7]}] {(s.get('date') or '')[:10]} {s.get('subject', '')}")
        for d in (s.get("decisions") or []):
            body.append(f"    · {d}")
    return redact_secrets("\n".join(body))


def export(project, target, fmt="madr", vault=None):
    """CLI 入口:collect_segments → to_adr → 返回 (输出/写盘提示, error)。零 LLM、不触网。"""
    from .blame import _parse_target, collect_segments
    from .cache import Cache
    from .config import CACHE_DB_PATH, load_config
    pp = Path(project).resolve()
    file, start, end = _parse_target(target)
    cache = Cache(CACHE_DB_PATH)
    try:
        segs = collect_segments(cache, pp, file, start, end)
    finally:
        cache.close()
    if not segs:
        return None, f"{file} 没有可用的提交历史,无从导出 ADR。"
    out = to_adr(target, segs, fmt=fmt)
    if vault:
        from . import report
        path = report.write_report(load_config()["vault_path"], pp.name,
                                   "adr-" + file.replace("/", "_"), out)
        return f"ADR 已写入:{path}", None
    return out, None


def adr_export_cmd(args):
    """零 LLM:某段代码真实决策史 → MADR/Nygard markdown,逐字引真实 commit。"""
    out, err = export(args.project, args.target, fmt=args.format, vault=args.vault)
    if err:
        print(f"错误:{err}", file=sys.stderr)
        return 2
    print(out)
    return 0
