"""开工简报(Boot Brief):开工前把『你上次停在哪』端到面前。
读本地 cache + git log(理解债),不调 LLM、不出网——补『日常化』最大短板。"""
from datetime import datetime, timezone

from . import debt as debt_mod
from .gitlog import collect_commit_files, commit_body, parse_breadcrumbs


def _debt_block(board):
    """理解债 top 3:认知循环的回喂出口(债量 → 简报 → 你回看 → 债降)。"""
    if not board:
        return []
    peak = board[0]["debt"] or 1
    lines = ["## 理解债 top 3", "",
             "_AI 改得多、你回看少的模块。回看信号仅含隧道 serve 模式。_", ""]
    for r in board:
        bar = "█" * max(1, round(r["debt"] / peak * 5))
        cap = f"·胶囊{r['caps_filled']}/{r['caps_total']}" if r["caps_total"] else ""
        lines.append(f"- `{r['file']}`  改{r['churn']}·回看{r['reviewed']}/"
                     f"{r['commits']}{cap}  {bar}")
        if r["last_decision"]:
            lines.append(f"  上次决定:{r['last_decision']}")
    lines.append("")
    return lines


def _breadcrumb_coverage(project_path, n=20):
    """最近 n 个 commit 有几个带 Vibe-Decision/Watch 面包屑(零 LLM)。
    返回 (带面包屑数, 统计 commit 数);无 git 历史返回 None。"""
    commits, err = collect_commit_files(project_path)
    if err or not commits:
        return None
    recent = commits[-n:]
    got = sum(1 for c in recent
              if any(parse_breadcrumbs(commit_body(project_path, c["sha"]))))
    return got, len(recent)


def build_brief(cache, project, project_full):
    """组装开工简报 markdown。project=项目名(daily/capsules 键),
    project_full=项目绝对路径(commit_narratives 键)。"""
    lines = [f"# {project} 开工简报", ""]
    today = datetime.now(timezone.utc).astimezone().date()
    lines += _debt_block(
        debt_mod.debt_board(project_full, project, cache, today, top=3))

    last = cache.latest_daily(project)
    lines += ["## 你上次停在哪", ""]
    if last:
        lines.append(f"_{last['date']}_:{last['overview']}")
        if last["decision"]:
            lines += ["", f"> 上次的决定 — {last['decision']}"]
    else:
        lines.append("(还没有任何日报——先跑一次 `vibetrace digest`。)")
    lines.append("")

    pending = cache.pending_capsules(project)
    if pending:
        lines += ["## 待验证的预测", ""]
        # 只端出最该验证的几枚(按 open_date 最久未答优先),其余折叠,
        # 防止久不回填时简报自己堆成新信息墙
        for cap in pending[:5]:
            lines.append(f"- (`{cap['sha'][:7]}`)你曾担心:「{cap['risk']}」"
                         "——现在验证了吗?")
        if len(pending) > 5:
            lines.append(f"- 另有 {len(pending) - 5} 枚待验证(暂折叠)")
        lines.append("")

    loops = cache.recent_open_loops(project_full)
    if loops:
        lines += ["## 悬而未决", ""]
        lines += ["- " + l for l in loops[:5]]   # 削峰,别堆成新信息墙
        if len(loops) > 5:
            lines.append(f"- 另有 {len(loops) - 5} 条(暂折叠)")
        lines.append("")

    cov = _breadcrumb_coverage(project_full)
    if cov:
        got, total = cov
        lines += ["## 决策面包屑", ""]
        if got:
            lines.append(f"近 {total} 个 commit 有 {got} 个带 Vibe-Decision/Watch"
                         "——ask/graph 据此更接地。")
        else:
            lines.append(f"近 {total} 个 commit 都没留面包屑。在 CLAUDE.md 加一句"
                         "「关键取舍留 `Vibe-Decision:`」让 agent 自动留,ask/graph 更准。")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
