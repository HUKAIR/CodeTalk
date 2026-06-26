"""逐字引用保真自检(dev-only,零 LLM):vibetrace 展示的「引用」是否逐字真实存在于真实来源。

护城河钉「零-LLM 确定性逐字接地」——本脚本出可复算数 substantiate 它,**非**幻觉检测器。
两类引用(均确定性、零 LLM、纯本地):
  (a) 面包屑:narrative.decisions/risks 里来自 `Vibe-Decision:`/`Vibe-Watch:` 的条目,
      对照**真实 commit body** 逐字核(源头干净,无会话变换)。
  (b) evidence 会话原话锚点:对照**当下重扫的真实会话**(scan_sessions),逐字/分段核
      (对 head_tail 截断鲁棒:按 `…` 分段,每段须是 live 文本子串);会话已删 → dangling。
诚实边界:只报「逐字无据(高精度低召回零成本)」,**不**宣称「检出所有幻觉/语义忠实」。
比较前对两侧都过 redact_secrets,与落盘脱敏对齐。用法:python3 scripts/citation_audit.py [project]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vibetrace import sessions                                      # noqa: E402
from vibetrace.cache import Cache                                   # noqa: E402
from vibetrace.config import CACHE_DB_PATH, redact_secrets          # noqa: E402
from vibetrace.gitlog import collect_commit_files, parse_breadcrumbs  # noqa: E402


def audit_breadcrumbs(items):
    """items: [{sha, dec_expected, risk_expected, decisions, risks}](expected 已脱敏)。
    每条面包屑须逐字在对应 narrative 字段(decision→decisions、watch→risks)。→ 审计 dict。"""
    out = {"total": 0, "verified": 0, "mismatches": []}
    for it in items:
        for kind, exp_key, store_key in (("decision", "dec_expected", "decisions"),
                                         ("risk", "risk_expected", "risks")):
            stored = it.get(store_key) or []
            for text in it.get(exp_key) or []:
                out["total"] += 1
                if text in stored:
                    out["verified"] += 1
                else:
                    out["mismatches"].append(
                        {"sha": it["sha"], "kind": kind, "text": text[:80]})
    return out


def audit_evidence(items):
    """items: [{sha, session_id, stored:[已脱敏原话], live:[已脱敏当下会话片段] | None}]。
    live=None → 会话已删/不可重扫 = dangling;否则 stored 按 `…` 分段须全为 live 子串。→ 审计 dict。"""
    out = {"total": 0, "verified": 0, "dangling": 0, "mismatches": []}
    for it in items:
        live = it.get("live")
        hay = "\n".join(live) if live else None
        for q in it.get("stored") or []:
            out["total"] += 1
            if live is None:
                out["dangling"] += 1
                continue
            frags = [f.strip() for f in q.split("…") if f.strip()]
            if frags and all(f in hay for f in frags):
                out["verified"] += 1
            else:
                out["mismatches"].append(
                    {"sha": it["sha"], "session_id": it.get("session_id"), "quote": q[:80]})
    return out


def main(project="."):
    pp = Path(project).resolve()
    commits, err = collect_commit_files(pp)
    if err:
        print(f"git 错误:{err}", file=sys.stderr)
        return 1
    cache = Cache(CACHE_DB_PATH)
    bc_items, narrated = [], []
    for c in commits:
        n = cache.get_narrative(c["sha"])
        if not isinstance(n, dict):
            continue
        narrated.append((c, n))
        decs, watches = parse_breadcrumbs(c.get("body", ""))
        bc_items.append({
            "sha": c["sha"][:7],
            "dec_expected": [redact_secrets(d) for d in decs],
            "risk_expected": [redact_secrets(w) for w in watches],
            "decisions": n.get("decisions") or [],
            "risks": n.get("risks") or [],
        })
    summaries, _serr = sessions.scan_sessions(pp, None, cache)
    by_sid = {}
    for s in summaries:
        sid = s.get("session_id")
        if sid:
            by_sid.setdefault(sid, []).extend(
                (s.get("prompts") or []) + (s.get("excerpts") or []))
    ev_items = []
    for c, n in narrated:
        for e in (n.get("evidence") or []):
            sid = e.get("session_id")
            stored = (e.get("prompts") or []) + (e.get("excerpts") or [])
            live = [redact_secrets(q) for q in by_sid[sid]] if sid in by_sid else None
            ev_items.append({"sha": c["sha"][:7], "session_id": sid,
                             "stored": stored, "live": live})
    cache.close()
    br, ev = audit_breadcrumbs(bc_items), audit_evidence(ev_items)
    print(f"# 逐字引用保真自检 · {pp.name}(零 LLM)\n")
    bt = br["total"] or 1
    print(f"面包屑引用(Vibe-Decision/Watch 对 commit body):{br['verified']}/{br['total']}"
          f" = {100 * br['verified'] / bt:.1f}% 逐字可验")
    et = ev["total"] or 1
    print(f"evidence 原话锚点(对当下会话):           {ev['verified']}/{ev['total']}"
          f" = {100 * ev['verified'] / et:.1f}% 逐字可验"
          f"(会话已删 dangling {ev['dangling']})")
    for m in br["mismatches"][:8]:
        print(f"  ⚠ 面包屑无据 [{m['sha']}] {m['kind']}: {m['text']}")
    for m in ev["mismatches"][:8]:
        print(f"  ⚠ evidence 无据 [{m['sha']}] {m['quote']}")
    print("\n注:只验「逐字无据」(高精度低召回零成本),非幻觉检测/语义忠实。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
