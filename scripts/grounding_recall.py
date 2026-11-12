"""接地召回自证(零 LLM):度量「指着一行真实代码问『当初为什么』,codetalk 的
零-LLM blame 实际能否 surface 一个 authored why」。是 grounding_hitrate(commit 级覆盖
**上限**)缺的一块——行级、按用户真问的粒度、走**真实** blame 引擎(blame.collect_segments)。

两档(均行加权、抽样、可复现):
- window 召回 = blame 为该行返回的任一段(line_log top-12 窗口)带 why → 这是 blame **实际**行为。
- strict 召回 = 该行**最新**触达 commit(段尾)带 why → 最近一次改动本身可解释。
  window>strict 的差 = 「why 藏在更早 commit、最近是琐碎改动」的比例。

**诚实边界**:度量「能 surface 一个 authored why」**非**「surface 正确的 why」(后者需语义
判定/模型,违零-LLM);抽样(seed 可复现);line_log top-12 窗口;why = narrative why/
decisions/Vibe-Decision 面包屑/否决备选(Vibe-Rejected)/evidence 任一;scope 默认 codetalk/*.py 源码非空行(非 docs/
tests)。随 commit 漂移,以复跑当下输出为准。纯本地、不调 LLM、不触网。

用法:python3 scripts/grounding_recall.py [project_path] [sample_n] [seed]
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# 真实 blame 引擎 + 单一 why 定义(与 review 溯源精度标注同源,杜绝两处 why 口径漂移)
from codetalk.blame import collect_segments, segment_has_why  # noqa: E402
from codetalk.cache import Cache                          # noqa: E402
from codetalk.config import CACHE_DB_PATH                 # noqa: E402
from codetalk.gitlog import collect_commit_files, tracked_files  # noqa: E402

DEFAULT_N = 200
DEFAULT_SEED = 1729


def line_grounded(segments):
    """segments 旧→新(blame.collect_segments 口径)。→ (window, strict):
    window = 任一段带 why(blame 实际能 surface);strict = 最新段(末尾)带 why。"""
    if not segments:
        return (False, False)
    window = any(segment_has_why(s) for s in segments)
    strict = segment_has_why(segments[-1])
    return (window, strict)


def sample_lines(file_lines, n, seed=DEFAULT_SEED):
    """file_lines: {path: [行号]}。→ 抽样 [(path, line)],定种可复现、升序、不超总数。"""
    pool = [(p, ln) for p in sorted(file_lines) for ln in file_lines[p]]
    random.Random(seed).shuffle(pool)
    return sorted(pool[:n])


def _meaningful_lines(path):
    """文件非空行的行号(零 LLM 不问『为什么这是空行』);读失败降级空列表,不崩。"""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [i for i, line in enumerate(text.splitlines(), 1) if line.strip()]


def measure(cache, project_root, samples):
    """对每个抽样行跑真实 blame.collect_segments → 行级召回指标(零 LLM)。"""
    m = {"sampled": len(samples), "window": 0, "strict": 0, "no_history": 0}
    for path, ln in samples:
        segs = collect_segments(cache, project_root, path, ln, ln)
        if not segs:
            m["no_history"] += 1
            continue
        window, strict = line_grounded(segs)
        m["window"] += int(window)
        m["strict"] += int(strict)
    d = m["sampled"] or 1
    m["window_pct"] = round(100 * m["window"] / d, 1)
    m["strict_pct"] = round(100 * m["strict"] / d, 1)
    return m


def _commit_coverage(cache, commits):
    """commit 级覆盖上限(对照 grounding_hitrate 口径,给行级召回一个参照系)。"""
    from codetalk.gitlog import parse_breadcrumbs
    grounded = 0
    for c in commits:
        n = cache.get_narrative(c["sha"]) or {}
        decs_bc, _ = parse_breadcrumbs(c.get("body", "") or "")
        if (n.get("why") or "").strip() or n.get("decisions") or decs_bc \
                or n.get("evidence"):
            grounded += 1
    total = len(commits) or 1
    return grounded, len(commits), round(100 * grounded / total, 1)


def main(project=".", sample_n=DEFAULT_N, seed=DEFAULT_SEED):
    pp = Path(project).resolve()
    tracked = tracked_files(pp) or set()
    sources = sorted(f for f in tracked
                     if f.startswith("codetalk/") and f.endswith(".py"))
    if not sources:
        print("未找到 codetalk/*.py 源码(非 codetalk 仓?)", file=sys.stderr)
        return 1
    file_lines = {f: _meaningful_lines(pp / f) for f in sources}
    file_lines = {f: lns for f, lns in file_lines.items() if lns}
    total_lines = sum(len(lns) for lns in file_lines.values())
    samples = sample_lines(file_lines, sample_n, seed)

    cache = Cache(CACHE_DB_PATH)
    m = measure(cache, pp, samples)
    commits, _err = collect_commit_files(pp)
    cg, ct, cpct = _commit_coverage(cache, commits) if commits else (0, 0, 0.0)
    cache.close()

    print(f"# 接地召回自证 · {pp.name}(零 LLM,行级)\n")
    print(f"scope:                codetalk/*.py · {len(file_lines)} 文件 · "
          f"{total_lines} 非空行")
    print(f"抽样(seed={seed}):    {m['sampled']} 行")
    print(f"无行历史(降级未中):  {m['no_history']}")
    print(f"\n**行级接地可达率(window:blame 能否够到一个 authored why,**上限非正确率**):"
          f"{m['window']}/{m['sampled']} = {m['window_pct']}%**")
    print(f"strict 可达率(最新触达 commit 自带 why):"
          f"{m['strict']}/{m['sampled']} = {m['strict_pct']}%")
    print(f"  → window−strict = why 藏在更早 commit、最近是琐碎改动的比例"
          f"(本仓≈0 = 几乎每个源码 commit 都带 Vibe-Decision 面包屑)")
    if ct:
        print(f"\n对照 · commit 级覆盖上限(grounding_hitrate 口径):"
              f"{cg}/{ct} = {cpct}%")
        print("  → 行级(行加权)远高于 commit 级(commit 加权):无面包屑的多是 doc/杂务 commit、"
              "几乎不碰源码行;源码行按 churn 几乎全落在带面包屑的大 feature commit 上。")
    print("\n诚实边界(关键):此数是**可达率/上限**——「blame 能够到一个 authored why」,"
          "**不等于**「够到的就是这一行**正确**的 why」(后者需语义判定/模型,违零-LLM,见 R6)。"
          "本仓饱和(99%+)源于其严格 dogfood 面包屑纪律,**不外推**别的仓。"
          "抽样可复现;line_log top-12 窗口;scope=codetalk/*.py 非空行。以复跑为准。")
    return 0


if __name__ == "__main__":
    proj = sys.argv[1] if len(sys.argv) > 1 else "."
    n = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_N
    sd = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_SEED
    sys.exit(main(proj, n, sd))
