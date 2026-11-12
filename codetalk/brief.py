"""开工简报(Boot Brief):开工前把『你上次停在哪』端到面前。
读本地 cache + git log(理解债),不调 LLM、不出网——补『日常化』最大短板。"""
from datetime import date, datetime, timezone
from pathlib import Path

from . import debt as debt_mod
from .config import redact_secrets
from .gitlog import (collect_commit_files, commit_body, has_decision_notes,
                     parse_breadcrumbs)


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
    """最近 n 个 commit 有几个带 Vibe-* 决策记录(零 LLM)。
    返回 (带决策记录数, 统计 commit 数);无 git 历史返回 None。"""
    commits, err = collect_commit_files(project_path)
    if err or not commits:
        return None
    recent = commits[-n:]
    got = sum(1 for c in recent          # body 已随批量 git log 取回,不再逐 commit git show
              if has_decision_notes(c.get("body", "")))
    return got, len(recent)


def build_brief(cache, project, project_full):
    """组装开工简报 markdown。project=项目名(daily/capsules 键),
    project_full=项目绝对路径(commit_narratives 键)。"""
    lines = [f"# {project} 开工简报", ""]
    today = datetime.now(timezone.utc).astimezone().date()
    lines += _debt_block(
        debt_mod.debt_board(project_full, cache, today, top=3))

    last = cache.latest_daily(project_full)
    lines += ["## 你上次停在哪", ""]
    if last:
        lines.append(f"_{last['date']}_:{last['overview']}")
        if last["decision"]:
            lines += ["", f"> 上次的决定 — {last['decision']}"]
    else:
        lines.append("(还没有任何日报——先跑一次 `codetalk digest`。)")
    lines.append("")

    pending = cache.pending_capsules(project_full)
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
        lines += ["## 决策记录", ""]
        if got:
            lines.append(f"近 {total} 个 commit 有 {got} 个带 Vibe-* 决策记录"
                         "——ask/review 据此更接地,Vibe-Decision 同时进入 graph。")
        else:
            lines.append(f"近 {total} 个 commit 都没留决策记录。在 agent 配置文件加一句"
                         "「关键取舍留 `Vibe-Decision:`」让 agent 自动留,ask/review 更准。")
        lines.append("")

    return redact_secrets("\n".join(lines).rstrip() + "\n")


TOP_DEBT_PROJECTS = 5


def _shorten(path):
    """~/x 代替 home,终端更短。带 / 边界守卫:/home/userX 不算 /home/u 的子路径。"""
    home, s = str(Path.home()), str(path)
    if s == home or s.startswith(home + "/"):
        return "~" + s[len(home):]
    return s


def _overview_row(name, path, pending, board, today):
    """单项目紧凑块。pending=pending_capsules(最久在前);board=debt_board(top=1)。"""
    lines = [f"## {name}  {_shorten(path)}"]
    if pending:
        oldest = pending[0]
        try:
            days = (today - date.fromisoformat(oldest["sealed_date"])).days
            since = f"(最久 {days} 天前)"
        except (ValueError, TypeError):
            since = ""  # 容错:坏日期不崩,省掉天数
        lines.append(f"- 待验证预测 {len(pending)} 枚{since}:「{oldest['risk']}」")
    if board:
        r = board[0]
        lines.append(f"- 理解债 top:`{r['file']}`(债 {r['debt']})")
    return lines


def _days_sealed(sealed_date, today):
    """已封天数;坏日期容错返回 None(到期胶囊仍要列,只是省天数)。"""
    try:
        return (today - date.fromisoformat(sealed_date)).days
    except (ValueError, TypeError):
        return None


def _is_verbatim_watch(project, sha, risk):
    """该 risk 是否逐字来自 commit 的 Vibe-Watch 面包屑(确定性,零-LLM)。
    commit_body 失败 → '' → 无 watches → 视为非逐字(LLM 预测),降级不崩。
    两侧同口径脱敏:cache 里的 risk 经 enrich redact_data 已脱敏,watches 来自原始 body,
    含 secret 形的手写 Watch 否则会因 [REDACTED] 不等而误判成 🤖 AI 预测(与 _seal 同口径)。"""
    _decs, watches = parse_breadcrumbs(commit_body(project, sha))
    return redact_secrets(risk) in {redact_secrets(w) for w in watches}


def _watch_block(name, path, pending, opened, filled, today):
    """单项目待回填块:risk + 已封天数 + 回填率(护栏)。逐字 Vibe-Watch(你亲手标的)排前
    标 🎯,LLM 预测 risk 标 🤖 在后——优先回面你真在意的,别被 LLM 预测噪声稀释。"""
    rate = f"{filled}/{opened}" if opened else "0/0"
    lines = [f"## {name}  {_shorten(path)}",
             f"_回填率 {rate}_", ""]
    tagged = [(_is_verbatim_watch(path, c["sha"], c["risk"]), c) for c in pending]
    tagged.sort(key=lambda t: not t[0])          # 逐字 Watch(True)排前
    for verbatim, cap in tagged:
        days = _days_sealed(cap["sealed_date"], today)
        since = f"(已封 {days} 天)" if days is not None else ""
        tag = "🎯 你标的" if verbatim else "🤖 AI 预测"
        lines.append(f"- {tag}(`{cap['sha'][:7]}`)你曾担心:「{cap['risk']}」"
                     f"{since}——现在验证了吗?")
    lines.append("")
    return lines


def build_watch(cache, projects, today):
    """跨项目 watch 收件箱:列出所有项目里『已到期开启、未回填』的胶囊,零 LLM。
    预测-验证闭环的日常入口;回填率是护栏指标,北极星=回面后实际处理率。
    projects=绝对路径列表(cache.distinct_projects())。返回已脱敏 markdown。"""
    rows = []
    for p in projects:
        if not Path(p).is_dir():
            continue  # 失效路径静默跳过,不计数
        pending = cache.pending_capsules(p)
        if not pending:
            continue
        opened, filled = cache.capsule_fill_stats(p)
        rows.append({"path": p, "name": Path(p).name, "pending": pending,
                     "opened": opened, "filled": filled})

    if not rows:
        return ("# 待验证收件箱\n\n暂时没有待回填的预测——"
                "胶囊到期后会出现在这里,届时回头验证当初的担心是否成真。\n")

    rows.sort(key=lambda x: len(x["pending"]), reverse=True)  # 待办多的在前
    total = sum(len(x["pending"]) for x in rows)
    lines = [f"# 待验证收件箱 · {total} 枚待回填", ""]
    for x in rows:
        lines += _watch_block(x["name"], x["path"], x["pending"],
                              x["opened"], x["filled"], today)
    return redact_secrets("\n".join(lines).rstrip() + "\n")


def build_overview(cache, projects, today):
    """跨项目注意力路由:有到期胶囊的 + 理解债最高的 K 个,零 LLM。
    projects=绝对路径列表(cache.distinct_projects())。返回已脱敏 markdown。"""
    live = []
    for p in projects:
        if not Path(p).is_dir():
            continue  # 失效路径静默跳过:不计数、不进 footer
        board = debt_mod.debt_board(p, cache, today, top=1)
        live.append({
            "path": p, "name": Path(p).name,
            "pending": cache.pending_capsules(p), "board": board,
            "peak": board[0]["debt"] if board else 0,
        })

    by_debt = sorted(live, key=lambda x: x["peak"], reverse=True)
    debt_in = {x["path"] for x in by_debt[:TOP_DEBT_PROJECTS] if x["peak"] > 0}
    shown = [x for x in live if x["pending"] or x["path"] in debt_in]
    shown.sort(key=lambda x: (len(x["pending"]), x["peak"]), reverse=True)

    if not shown:
        return ("# 跨项目总览\n\n没有需要注意的项目"
                "——先在某个项目跑 `codetalk digest`。\n")

    lines = [f"# 跨项目总览 · {len(shown)} 个项目待办", ""]
    for x in shown:
        lines += _overview_row(x["name"], x["path"], x["pending"],
                               x["board"], today)
        lines.append("")
    omitted = len(live) - len(shown)
    if omitted:
        lines.append(f"_另有 {omitted} 个存活项目未入榜"
                     "(债较低、无到期胶囊),已省略。_")
    return redact_secrets("\n".join(lines).rstrip() + "\n")
