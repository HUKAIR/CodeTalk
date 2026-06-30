"""接地命中率自证(零 LLM):度量本仓有多少 commit 能被确定性接地回答『当初为什么这么写』。

覆盖上限 = 有 narrative why/decisions、或 commit 正文含 Vibe-Decision 面包屑、或有 evidence
原话锚点 的 commit 占比。这是护城河的诚实天花板(回答 ROADMAP open Q『接地命中率上限』),
也是 review-entry 扩面 / grounding-eval / 本地模型 等下游项是否启动的共同闸门。

纯本地、不调 LLM、不触网。用法:python3 scripts/grounding_hitrate.py [project_path]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from codetalk.cache import Cache                                  # noqa: E402
from codetalk.config import CACHE_DB_PATH                         # noqa: E402
from codetalk.gitlog import collect_commit_files, parse_breadcrumbs  # noqa: E402


def measure(cache, commits):
    """commits: [{sha, body, ...}]。→ 接地覆盖指标 dict(零 LLM)。
    grounded = 任一确定性接地源存在(narrative why/decisions、Vibe-Decision 面包屑、evidence 锚点)。"""
    m = {"total": len(commits), "narrated": 0, "breadcrumb": 0,
         "evidence": 0, "grounded": 0}
    for c in commits:
        n = cache.get_narrative(c["sha"]) or {}
        decs_bc, _ = parse_breadcrumbs(c.get("body", "") or "")
        has_bc = bool(decs_bc)
        why = (n.get("why") or "").strip()
        decs = n.get("decisions") or []
        ev = n.get("evidence") or []
        if n:
            m["narrated"] += 1
        if has_bc:
            m["breadcrumb"] += 1
        if ev:
            m["evidence"] += 1
        if why or decs or has_bc or ev:        # 任一确定性接地源 → 可回答 why
            m["grounded"] += 1
    t = m["total"] or 1
    m["coverage_pct"] = round(100 * m["grounded"] / t, 1)
    m["narrated_pct"] = round(100 * m["narrated"] / t, 1)
    return m


def main(project="."):
    pp = Path(project).resolve()
    commits, err = collect_commit_files(pp)
    if err:
        print(f"git 错误:{err}", file=sys.stderr)
        return 1
    cache = Cache(CACHE_DB_PATH)
    m = measure(cache, commits)
    cache.close()
    print(f"# 接地命中率自证 · {pp.name}(零 LLM)\n")
    print(f"commit 总数:           {m['total']}")
    print(f"有叙事:               {m['narrated']} ({m['narrated_pct']}%)")
    print(f"有 Vibe-Decision 面包屑:{m['breadcrumb']}")
    print(f"有 evidence 原话锚点:   {m['evidence']}")
    print(f"\n**可确定性接地回答 why(覆盖上限):"
          f"{m['grounded']}/{m['total']} = {m['coverage_pct']}%**")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
