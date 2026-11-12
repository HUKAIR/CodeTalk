"""ADR 导出(零 LLM):把一段代码的真实决策史确定性渲染成 MADR / Nygard / CycloneDX。

区别于手写 ADR 生态(adr-tools / Log4brains / pyadr 全手写、无一从 git 自动挖):codetalk 从
真实 commit/决策**自动**导出,「来源」段附真实 commit SHA + 逐字原话(可核验,非 LLM 反推)——
「别人要你手写 ADR,codetalk 从真实记录自动导出且逐字接地」。复用 blame.collect_segments;
纯字符串拼接、零 LLM、不触网、出口脱敏、绝不崩。

cyclonedx 格式输出 CycloneDX 1.5 base schema 子集(bomFormat/specVersion/components),
让决策史能接进 AIBOM 生态(CISA/G7 SBOM for AI、CycloneDX AI 扩展)。timestamp 取最新
commit 时间保证 reproducible(同输入同输出),不假装符合 modelCard/formulation 等 AI 专门段
——codetalk 跟踪的是代码决策不是模型,硬塞会编造。
"""
import json
import sys
import uuid
from pathlib import Path

from .config import redact_data, redact_secrets

FORMATS = ("madr", "nygard", "cyclonedx")


def _bullets(items):
    uniq = [str(x) for x in dict.fromkeys(items) if str(x).strip()]
    return ["- " + x for x in uniq] or ["-(未记)"]


def _to_cyclonedx(target, segments):
    """CycloneDX 1.5 base schema 子集——每个 commit 一个 component,逐字保留决策原话。
    serialNumber/timestamp 据 target+segments 哈希确定性生成,同输入字节级 reproducible。"""
    latest_ts = ""
    for s in reversed(segments):
        if s.get("date"):
            latest_ts = s["date"]
            break
    # uuid5(确定性:同输入同 UUID,仍字节级 reproducible)且是合法 RFC-4122 v5——
    # 裸 sha256 切片虽过 CycloneDX 宽松 regex,但 version/variant nibble 不合规,严格校验会拒。
    seed = target + "|" + "|".join(s.get("sha", "") for s in segments)
    serial = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, seed)}"
    components = []
    for s in segments:
        props = []
        for d in (s.get("decisions") or []):
            props.append({"name": "codetalk:decision", "value": d})
        for r in (s.get("rejected") or []):
            props.append({"name": "codetalk:rejected", "value": r})
        for r in (s.get("risks") or []):
            props.append({"name": "codetalk:risk", "value": r})
        components.append({
            "type": "data", "bom-ref": s.get("sha", ""),
            "name": s.get("subject", "") or target,
            "description": s.get("why") or "",
            "properties": props,
        })
    bom = {
        "bomFormat": "CycloneDX", "specVersion": "1.5",
        "serialNumber": serial, "version": 1,
        "metadata": {
            "timestamp": latest_ts,
            # 1.5 非废弃 tools 形态:{components:[...]};legacy tool[] 不允许 description
            # 字段(additionalProperties:false),用 component 形态既携带 description 又过官方 schema
            "tools": {"components": [
                {"type": "application", "name": "codetalk",
                 "description": "zero-LLM commit decision provenance"}]},
            "component": {"type": "application", "name": target},
        },
        "components": components,
    }
    # 脱敏在 json.dumps 之前(对原始字符串叶子,见 redact_data 注释):dumps 转义引号会
    # 让 key="value" 形式 secret 漏过 redact_secrets;故 redact 结构而非序列化后文本
    return json.dumps(redact_data(bom), ensure_ascii=False, indent=2)


def to_adr(target, segments, fmt="madr"):
    """segments(旧→新,blame.collect_segments 输出)→ 一份 markdown ADR(或 JSON BOM)。零 LLM、落地前脱敏。"""
    if fmt == "cyclonedx":
        return _to_cyclonedx(target, segments)
    whys = [s["why"] for s in segments if s.get("why")]
    decisions = [d for s in segments for d in (s.get("decisions") or [])]
    rejected = [r for s in segments for r in (s.get("rejected") or [])]
    risks = [r for s in segments for r in (s.get("risks") or [])]
    title = (segments[-1].get("subject") if segments else "") or target
    context = whys or ["(无叙事;先跑 codetalk digest / enrich 富集)"]
    # 被否决备选 = ADR 的「Considered Options」本源;仅在有否决记录时出该段(不撑空节)
    considered = (["", "## Considered Options(被否决的备选)", *_bullets(rejected)]
                  if rejected else [])
    if fmt == "nygard":
        body = ["# " + title, "", "## Status", "accepted", "",
                "## Context", *context, "",
                "## Decision", *_bullets(decisions), *considered, "",
                "## Consequences", *_bullets(risks)]
    else:                                         # MADR(默认)
        body = ["# " + title, "", "- Status: accepted", "",
                "## Context and Problem Statement", *context, "",
                "## Decision Outcome", *_bullets(decisions), *considered, "",
                "## Consequences", *_bullets(risks)]
    body += ["", "## 来源(真实 commit,逐字可核验)", f"_目标:{target}_"]
    for s in segments:                            # 每个 commit 的 SHA + 逐字决策/否决原话锚点
        body.append(f"- [{s['sha'][:7]}] {(s.get('date') or '')[:10]} {s.get('subject', '')}")
        for d in (s.get("decisions") or []):
            body.append(f"    · {d}")
        for r in (s.get("rejected") or []):
            body.append(f"    · (否决){r}")
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
