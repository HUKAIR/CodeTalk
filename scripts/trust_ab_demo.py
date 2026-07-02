"""A/B 信任对照 demo:同一 commit,codetalk 引真实记录 vs LLM 从 diff 反推,用户自己判哪个更可信。

比 blind_test.py 更聚焦:不做泄漏标/脱敏分析,只做最直观的并排呈现——
适合发 HN/Reddit 或分享给外部受访者跑。无 key 降级为只列真实记录。

用法:python3 scripts/trust_ab_demo.py [项目] [N]
"""
import json
import random
import sys
from pathlib import Path
from string import Template

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from codetalk.cache import Cache                               # noqa: E402
from codetalk.config import (CACHE_DB_PATH, load_config,  # noqa: E402
                              redact_data, redact_secrets)
from codetalk.gitlog import (collect_commit_files, commit_diff,  # noqa: E402
                              parse_breadcrumbs, parse_rejected)
from codetalk.llm import LLMClient, LLMError                    # noqa: E402

DEFAULT_N = 5


def _real_record(cache, sha, body):
    """codetalk 的真实记录:叙事 + 面包屑 + 否决备选。"""
    parts = []
    narrative = cache.get_narrative(sha) or {}
    if narrative.get("why"):
        parts.append(f"Why: {narrative['why']}")
    for d in narrative.get("decisions") or []:
        parts.append(f"Decision: {d}")
    for r in narrative.get("rejected") or []:
        parts.append(f"Rejected: {r}")
    decs, _ = parse_breadcrumbs(body or "")
    for d in decs:
        if d not in parts:
            parts.append(f"Breadcrumb: {d}")
    for r in parse_rejected(body or ""):
        if f"Rejected: {r}" not in parts:
            parts.append(f"Rejected: {r}")
    return parts


def _llm_guess(llm, diff_text):
    """LLM 从纯 diff 反推 why（模拟 AI 考古）。"""
    if not llm or not diff_text:
        return None
    system = ("You are doing git archaeology. You only see a commit's diff — "
              "no commit message, no comments, no external context. "
              "Infer WHY the author made these changes and what alternatives "
              "they might have rejected. 3-5 sentences, be specific.")
    try:
        return llm.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": redact_data(diff_text)[:6000]},
        ])
    except Exception:
        return None


def _emit_html(pp, sample, cache, llm, out_path):
    """把 A/B 对照渲染成可交互、可分享的单页 HTML(零外链,出口脱敏)。→ 命中条数。"""
    items = []
    for c in sample:
        guess = _llm_guess(llm, commit_diff(pp, c["sha"]))
        if not guess:                        # 无 diff/反推失败 → 跳过,不摆空 A/B
            continue
        real = "\n".join(_real_record(cache, c["sha"], c.get("body", "")))
        coin = random.random() > 0.5         # 随机哪侧是真,避免位置泄露
        date = (c["date"].isoformat()[:10] if hasattr(c.get("date"), "isoformat")
                else str(c.get("date", ""))[:10])
        items.append({"sha": c["sha"][:7], "date": date,
                      "subject": c.get("subject", ""),
                      "a": real if coin else guess, "b": guess if coin else real,
                      "real": "a" if coin else "b"})
    data = redact_data({"items": items})     # 结构叶子脱敏(dumps 前)
    tpl = Path(__file__).resolve().parent.parent / "codetalk" / "trust_ab.html"
    html = Template(tpl.read_text(encoding="utf-8")).substitute(
        project=redact_secrets(pp.name),
        data=json.dumps(data, ensure_ascii=False))
    Path(out_path).write_text(redact_secrets(html), encoding="utf-8")  # 整页再兜底脱敏
    return len(items)


def main(project=".", n=DEFAULT_N, html_path=None):
    pp = Path(project).resolve()
    commits, err = collect_commit_files(pp)
    if err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    cache = Cache(CACHE_DB_PATH)
    has_record = [c for c in commits
                  if _real_record(cache, c["sha"], c.get("body", ""))]
    if not has_record:
        print("No commits with codetalk records found. Run `codetalk enrich` first.",
              file=sys.stderr)
        cache.close()
        return 1

    sample = has_record[-min(n * 3, len(has_record)):]
    random.seed(42)
    random.shuffle(sample)
    sample = sample[:n]

    cfg = load_config()
    try:
        llm = LLMClient(cfg)
    except LLMError:
        llm = None
        print("(No LLM key — showing real records only, no AI comparison)\n")

    if html_path:                            # 可分享的交互式 A/B 页(需 LLM 生成对照侧)
        if llm is None:
            print("--html needs an LLM key (A/B needs both sides). Set a key first.",
                  file=sys.stderr)
            cache.close()
            return 1
        count = _emit_html(pp, sample, cache, llm, html_path)
        cache.close()
        print(f"Wrote {count} commits → {html_path}")
        return 0

    # 无 key:没有对照的一侧,盲测不成立(否则一侧写死 "(no LLM)" 直接暴露哪个是真)。
    # 降级为纯展示真实记录,不摆 A/B 架子。
    if llm is None:
        print(f"# CodeTalk real records — {pp.name} ({len(sample)} commits)\n")
        print("Zero-LLM, verbatim from git. (Set an LLM key to run the A/B blind test.)\n---\n")
        for i, c in enumerate(sample, 1):
            sha7 = c["sha"][:7]
            date = (c["date"].isoformat()[:10] if hasattr(c.get("date"), "isoformat")
                    else str(c.get("date", ""))[:10])
            real = _real_record(cache, c["sha"], c.get("body", ""))
            subject = redact_secrets(c.get("subject", ""))
            print(f"## Commit {i}: [{sha7}] {date} {subject}\n")
            print(redact_secrets("\n".join(f"- {r}" for r in real)) + "\n\n---\n")
        cache.close()
        return 0

    print(f"# A/B Trust Demo — {pp.name} ({len(sample)} commits)\n")
    print("For each commit: **A** is one source, **B** is the other.")
    print("Which do you trust more? (The reveal is at the end.)\n")
    print("---\n")

    reveals = []
    for i, c in enumerate(sample, 1):
        sha7 = c["sha"][:7]
        date = (c["date"].isoformat()[:10] if hasattr(c.get("date"), "isoformat")
                else str(c.get("date", ""))[:10])
        real = _real_record(cache, c["sha"], c.get("body", ""))

        diff_text = commit_diff(pp, c["sha"])
        guess = _llm_guess(llm, diff_text)
        if not guess:                        # 该 commit 无 diff/反推失败 → 跳过,不摆空 A/B
            continue

        coin = random.random() > 0.5
        a_text = "\n".join(f"- {r}" for r in real) if coin else guess
        b_text = guess if coin else "\n".join(f"- {r}" for r in real)
        reveals.append("A = real record" if coin else "B = real record")

        # 输出设计为可公开分享(HN/Reddit)→ subject/real-record/guess 全脱敏后再打印
        subject = redact_secrets(c.get("subject", ""))
        print(f"## Commit {i}: [{sha7}] {date} {subject}\n")
        print(f"**Source A:**\n{redact_secrets(a_text)}\n")
        print(f"**Source B:**\n{redact_secrets(b_text)}\n")
        print(f"→ Which do you trust more, A or B?\n")
        print("---\n")

    print("## Reveal\n")
    for i, r in enumerate(reveals, 1):
        print(f"- Commit {i}: {r}")
    print(f"\nReal records = codetalk (zero-LLM, verbatim SHA citations)")
    print(f"Other = LLM inference from diff alone (no commit message given)")

    cache.close()
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    html_path = None
    if "--html" in args:                     # --html <path>:输出可分享的交互式对照页
        i = args.index("--html")
        html_path = args[i + 1] if i + 1 < len(args) else "codetalk-trust-ab.html"
        args = args[:i] + args[i + 2:]
    project = args[0] if args else "."
    n = int(args[1]) if len(args) > 1 else DEFAULT_N
    sys.exit(main(project, n, html_path))
