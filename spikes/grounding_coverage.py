"""dogfood:量化 vibetrace 对「找回当初 why」的**可核验接地覆盖率**(零 LLM、真实仓、可复跑)。

对最近一段 commit,统计有多少能拿到**你自己的一手材料**佐证「当初为什么」——
会话原话(经 align)/ 相关测试 / PR 讨论 / Vibe-Decision 面包屑——而非只能信 LLM 重述;
并列出「有改动却零可核验接地」的高风险 commit:理由丢失型踩坑的温床(对位用户1 积分 floor→round)。

这是把「实质解决」往「彻底」推的**诚实度量**:覆盖率越高,越不必依赖被只信 6 分的 LLM 重解释。
等真实使用积累(留面包屑 / 会话被捕获 / PR)后复跑,可看趋势上升。

用法:  python3 spikes/grounding_coverage.py [--project .] [--since "30 days ago"] [--with-pr]
零 LLM、只读;--with-pr 额外查 GitHub PR(数据出本机,opt-in)。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vibetrace import align, cursor_sessions, enrich, gitlog, sessions  # noqa: E402
from vibetrace.cache import Cache                                       # noqa: E402
from vibetrace.config import CACHE_DB_PATH                              # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=".")
    ap.add_argument("--since", default="30 days ago")
    ap.add_argument("--with-pr", action="store_true",
                    help="额外查 GitHub PR(数据出本机,opt-in)")
    args = ap.parse_args()
    proj = Path(args.project).resolve()

    commits, err = gitlog.collect_commit_files(proj, args.since)
    if err:
        print("git 出错:", err, file=sys.stderr)
        return 1
    if not commits:
        print(f"{args.since} 以来无 commit。")
        return 0

    cache = Cache(CACHE_DB_PATH)
    sess, _ = sessions.scan_sessions(proj, None, cache)             # Claude 会话(原话)
    csess, _ = cursor_sessions.scan_sessions(proj, None, cache)    # Cursor 会话(若本仓有)
    cache.close()
    align.align(commits, sess + (csess or []), proj)               # 软关联 → commit["matches"]

    n = len(commits)
    tally = {"原话": 0, "测试": 0, "PR": 0, "面包屑": 0, "接地": 0}
    at_risk = []
    for c in commits:
        has_quote = any(m["confidence"] == "high" for m in c.get("matches", []))
        has_test = bool(enrich._test_refs(str(proj), c))
        decs, watches = gitlog.parse_breadcrumbs(c.get("body", ""))
        has_bc = bool(decs or watches)
        has_pr = bool(enrich._pr_refs(c, str(proj))) if args.with_pr else False
        for k, v in (("原话", has_quote), ("测试", has_test),
                     ("PR", has_pr), ("面包屑", has_bc)):
            tally[k] += int(v)
        if has_quote or has_test or has_bc or has_pr:
            tally["接地"] += 1
        else:
            at_risk.append(c)

    pct = tally["接地"] * 100 // n
    print(f"# 可核验接地覆盖率(最近 {n} 个 commit · {args.since} 起 · 零 LLM)\n")
    print(f"可核验接地:{tally['接地']}/{n} = {pct}%  "
          "(有 ≥1 种你自己的一手材料佐证 why,不必只信 LLM)")
    print(f"  会话原话(align high):{tally['原话']}/{n}")
    print(f"  相关测试            :{tally['测试']}/{n}")
    print(f"  Vibe-Decision 面包屑:{tally['面包屑']}/{n}")
    print(f"  PR 讨论             :{tally['PR']}/{n}" if args.with_pr
          else "  PR 讨论             :(未开,加 --with-pr 查 GitHub)")
    print(f"\n高风险(零可核验接地 → 理由丢失型踩坑温床):{len(at_risk)} 个")
    for c in at_risk[:15]:
        print(f"  {c['sha'][:7]} {c['subject'][:60]}")
    if len(at_risk) > 15:
        print(f"  …另有 {len(at_risk) - 15} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main())
