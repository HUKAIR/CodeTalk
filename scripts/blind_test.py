"""护城河盲测(可复跑):纯 diff 反推 why vs vibetrace 引真实记录。

对位 README 那个手工 6-commit 盲测(此前明说『无单条复跑脚本』)——把它产品化:对任意仓取 N 个
带真实面包屑的 commit,把**脱敏后的纯 diff**(无 message/注释/上下文)喂 LLM 让它反推『当初为什么、
否决了什么』,跟 vibetrace 零-LLM 引的真实面包屑并排。

**判对错由人来,脚本不自动打分**——语义对错要么需 LLM-judge(R6 警告项、且削弱『零-LLM』招牌)、
要么字符串重叠(R6 已证伪 HANS 0.28),都拒。脚本只确定性做两件:① 并排呈现两侧;②**数据泄漏标**
(diff 是否已夹带 why 原文,词重叠启发式)——把 README 自己那条诚实 caveat『why 被一起 commit 进
diff』可计算化,用来标『对比被 diff 夹带污染』的条目。**泄漏标只测「why 原文是否字面落在 diff 里」,
不测「能否推断」**:故『未夹带』只表示字面没有(反推须靠推断,命中与否仍你来判);且对**短 why
(<4 字)或被改写的 why 会低估夹带、偏向『未夹带』**(即偏向利好护城河的方向,读时心里有数)。

红线:diff 发 LLM 前 `redact_data`(数据出本机仅 LLM 例外);无 key 降级为只列真实记录+泄漏标、
不跑反推;opt-in dev 脚本、出口已脱敏、仅 stdlib(difflib)+ 现有 LLM 封装、零新依赖。
用法:python3 scripts/blind_test.py [项目] [N]
"""
import difflib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vibetrace.config import load_config, redact_data           # noqa: E402
from vibetrace.gitlog import (collect_commit_files, commit_diff,  # noqa: E402
                              parse_breadcrumbs, parse_rejected)
from vibetrace.llm import LLMClient, LLMError                    # noqa: E402

DEFAULT_N = 6
_MIN_BLOCK = 4         # 词重叠最小连续匹配长度,滤短噪
_DIFF_BUDGET = 6000    # 喂 LLM 的 diff 上限字符(足够反推、控 token)
_FETCH_BUDGET = 200000  # 先取(近)全 diff 再脱敏,最后才截——截点只切已脱敏文本,杜绝跨界半截 secret


def _real_why(body):
    """commit 的真实 why = Vibe-Decision 决策 + Vibe-Rejected 否决备选(确定性、逐字)。"""
    decisions, _watches = parse_breadcrumbs(body or "")
    return decisions + [f"(否决){r}" for r in parse_rejected(body or "")]


def leakage(why_text, diff_text):
    """→ (ratio, label):why 原文有多少落在 diff 里(确定性词重叠启发式)。
    ratio = why 中处于「与 diff 的 ≥4 连续匹配块」内的字符占比。
    高=diff 已夹带 why(对比被污染);低=diff 查无该 why(纯 diff 反推只能编/推)。"""
    why_text = why_text or ""
    if not why_text:
        return 0.0, "无真实 why 文本"
    sm = difflib.SequenceMatcher(None, why_text, diff_text or "", autojunk=False)
    matched = sum(b.size for b in sm.get_matching_blocks() if b.size >= _MIN_BLOCK)
    ratio = matched / len(why_text)
    if ratio >= 0.6:
        label = "已夹带(diff 含大部分 why 原文 → 对比被污染,不算数)"
    elif ratio >= 0.25:
        label = "部分夹带"
    else:
        label = "未夹带 why 原文(反推须靠推断,命中与否你来判)"
    return ratio, label


def pick_commits(commits, n):
    """带真实面包屑(决策或否决备选)的 commit,取最新 n(commits 为旧→新),返回新→旧。"""
    crumbed = [c for c in commits if _real_why(c.get("body", ""))]
    return list(reversed(crumbed[-n:]))


def reconstruct_messages(diff_text):
    """只给 diff、不给任何 message/注释,让 LLM 反推 why(模拟纯 diff 的 git 考古)。"""
    system = ("你在做 git 考古:只看到某 commit 的 diff,没有 commit message、注释或任何外部上下文。"
              "仅据这份 diff 推断作者**当初为什么这么改、为什么这么选、否决了哪些备选**。"
              "直接给推断,别复述 diff 改了什么。3-5 句。")
    return [{"role": "system", "content": system},
            {"role": "user", "content": diff_text}]


def format_comparison(commit, real, reconstruction, ratio, label):
    sha = (commit.get("sha") or "")[:7]
    raw_date = commit.get("date")
    date = (raw_date.isoformat()[:10] if hasattr(raw_date, "isoformat")
            else str(raw_date or "")[:10])
    lines = [f"## [{sha}] {date} {commit.get('subject', '')}",
             "**vibetrace 引真实记录(零-LLM,逐字):**"]
    lines += [f"- {r}" for r in real] or ["-(无)"]
    lines += ["", "**纯 diff 反推(LLM,只给 diff):**",
              reconstruction or "(无 key,未跑反推)", "",
              f"_数据泄漏标(确定性,词重叠 {ratio:.0%}):{label}_", "",
              "→ **你来判**:反推是否命中真实 why?(脚本不自动判对错——语义需人)"]
    return "\n".join(lines)


def main(project=".", n=DEFAULT_N):
    pp = Path(project).resolve()
    commits, err = collect_commit_files(pp)
    if err:
        print(f"git 错误:{err}", file=sys.stderr)
        return 1
    picked = pick_commits(commits, n)
    if not picked:
        print("没有带真实面包屑的 commit 可盲测。", file=sys.stderr)
        return 1
    client = None
    try:
        client = LLMClient(load_config())
    except LLMError as exc:
        print(f"# 无 LLM(降级:只列真实记录+泄漏标,不跑反推):{exc}\n", file=sys.stderr)
    bands = {"已夹带": 0, "部分夹带": 0, "未夹带": 0}
    blocks = []
    for c in picked:
        real = _real_why(c.get("body", ""))
        # 先取(近)全 diff → 脱敏 → 最后才截:截点只切已脱敏文本,杜绝跨界半截 secret 漏出
        diff = redact_data(commit_diff(pp, c["sha"], char_budget=_FETCH_BUDGET))[:_DIFF_BUDGET]
        recon = ""
        if client:
            try:
                recon = client.chat(reconstruct_messages(diff))
            except LLMError as exc:
                recon = f"(反推失败:{exc})"
        ratio, label = leakage(" ".join(real), diff)
        bands["已夹带" if ratio >= 0.6 else "部分夹带" if ratio >= 0.25 else "未夹带"] += 1
        blocks.append(format_comparison(c, real, recon, ratio, label))
    print(f"# 护城河盲测 · {pp.name}(纯 diff 反推 vs vibetrace 真实记录)\n")
    print(f"N={len(picked)} · 数据泄漏标:未夹带 {bands['未夹带']} / 部分夹带 {bands['部分夹带']} / "
          f"已夹带 {bands['已夹带']}")
    print("(泄漏标=确定性词重叠启发式,**只测字面是否落在 diff、不测能否推断**;"
          "对短/改写 why 偏向『未夹带』即偏利好护城河,读时打折。反推对错逐条读对比、你来判。)\n")
    print("\n\n".join(blocks))
    return 0


if __name__ == "__main__":
    proj = sys.argv[1] if len(sys.argv) > 1 else "."
    num = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_N
    sys.exit(main(proj, num))
