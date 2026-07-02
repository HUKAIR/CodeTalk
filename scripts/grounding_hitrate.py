"""接地命中率自证(零 LLM):度量本仓有多少 commit 能被确定性接地回答『当初为什么这么写』。

两个口径,严格区分:
- **真实接地率(北极星候选)** = commit 正文含 Vibe-Decision/Vibe-Rejected 面包屑,或有
  evidence 逐字原话锚点 的占比。**只算逐字/面包屑,排除 enrich 的 LLM 生成叙事**——因为
  LLM 叙事可能编造,那正是护城河立论所在。这是"可点验证的真实来源"的诚实覆盖。
- **接地覆盖上限(较松)** = 上者再并上 narrative 的 LLM why/decisions。回答 ROADMAP open Q
  『接地命中率上限』,但含可幻觉成分,不宜当对外可信度或北极星。

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
    real_grounded = 逐字/面包屑接地(Vibe-* 面包屑 或 evidence 原话锚点),排除 LLM 叙事——北极星口径。
    grounded = real_grounded 再并上 narrative 的 LLM why/decisions,含可幻觉成分,是较松的覆盖上限。"""
    m = {"total": len(commits), "narrated": 0, "breadcrumb": 0,
         "evidence": 0, "grounded": 0, "real_grounded": 0}
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
        if has_bc or ev:                       # 逐字/面包屑 = 真实接地(可点验证,非 LLM 生成)
            m["real_grounded"] += 1
        if why or decs or has_bc or ev:        # 再并上 LLM 叙事 = 较松覆盖上限
            m["grounded"] += 1
    t = m["total"] or 1
    m["real_pct"] = round(100 * m["real_grounded"] / t, 1)
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
    print(f"有 Vibe-* 面包屑:       {m['breadcrumb']}")
    print(f"有 evidence 原话锚点:   {m['evidence']}")
    print(f"有叙事(含 LLM 生成):  {m['narrated']} ({m['narrated_pct']}%)")
    print(f"\n**★ 真实接地率(北极星 · 逐字/面包屑,可点验证,排除 LLM 叙事):"
          f"{m['real_grounded']}/{m['total']} = {m['real_pct']}%**")
    print(f"  接地覆盖上限(较松,含 LLM 叙事,不当对外可信度):"
          f"{m['grounded']}/{m['total']} = {m['coverage_pct']}%")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
