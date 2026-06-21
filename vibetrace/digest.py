"""digest 子命令 — git+会话 → 按日变更叙事日报。

从 commands.py 拆出:digest 体量最大(占该模块过半),独立成模块以守住
单模块 <300 行红线;commands.py 仅保留各命令的轻量分发。
"""
import calendar
import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import align, enrich, gitlog, report, sessions
from .cache import Cache
from .config import load_config
from .llm import LLMClient, LLMError

log = logging.getLogger("vibetrace")


def _since_to_dt(since):
    """Loose mirror of common 'git --since' phrases, for session file filtering."""
    parts = since.split()
    units = {"day": 1, "days": 1, "week": 7, "weeks": 7, "month": 30,
             "months": 30, "hour": 1 / 24, "hours": 1 / 24}
    try:
        if len(parts) >= 2 and parts[-1] == "ago" and parts[1] in units:
            return datetime.now(timezone.utc) - timedelta(
                days=float(parts[0]) * units[parts[1]])
        return datetime.fromisoformat(since).astimezone(timezone.utc)
    except ValueError:
        return None  # git understands it; we just skip mtime pre-filtering


def _shift(d, *, years=0, months=0):
    """同一日历日往前推 N 月/年;溢出日(如 3/31→2/28)夹紧到月末。"""
    m = d.month - 1 - months
    y = d.year - years + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def digest(args):
    from .commands import _cache_db_path, _fail  # 复用 commands 的轻量分发辅助
    started = time.time()
    cfg = load_config()
    if args.provider:
        cfg["provider"] = args.provider
    if args.model:
        cfg["model"] = args.model
    if args.vault:
        cfg["vault_path"] = args.vault
    project_path = Path(args.project).resolve()
    project = project_path.name        # 显示标题 / 输出文件名
    pkey = str(project_path)            # cache 键:绝对路径,同名项目不串

    commits, git_err = gitlog.collect_commits(
        project_path, args.since, cfg["diff_token_budget"])
    if git_err:
        return _fail(git_err)
    if not commits:
        print(f"{args.since} 以来没有 commit,无日报可写。")
        return 0

    cache = Cache(_cache_db_path())
    cache.rekey_project(project, pkey)   # 迁移旧 basename 键数据(一次性,幂等)
    session_list, session_err = sessions.scan_sessions(
        project_path, _since_to_dt(args.since), cache)
    if session_err:
        log.warning("会话层降级:%s", session_err)
    align.align(commits, session_list, project_path)

    try:
        llm = LLMClient(cfg)
    except LLMError as exc:
        return _fail(exc)
    # 回读上次运行后用户在 Obsidian 里勾选的胶囊答案,闭合预测-验证环
    report.read_capsule_answers(cfg["vault_path"], pkey, cache)
    # 运行前已缓存的 SHA:用于区分每天的缓存命中 vs 新算(按日页脚统计)
    pre_cached = {c["sha"] for c in commits if cache.get_narrative(c["sha"])}
    enrich.enrich_commits(commits, llm, cache, str(project_path))

    # 按 commit 日期分桶,一天一份日报:bound 住报告长度与概览输入,
    # 并让历史各天都进 daily_digests 缓存(修复回补时 On This Day 查不到)。
    by_day = {}
    for commit in commits:
        by_day.setdefault(commit["date"].date(), []).append(commit)

    days = []  # 先按日生成概览/胶囊,等 LLM 统计齐了再统一渲染
    for day in sorted(by_day):
        day_commits = by_day[day]
        date_str = day.isoformat()
        overview, decision, calls = enrich.make_overview(
            day_commits, llm, cache, str(project_path), date_str)
        cache.put_daily(pkey, date_str, overview, decision)
        for commit in day_commits:  # 以该天为「今日」封存,忠实重放胶囊时间线
            sealed = commit["date"].date().isoformat()
            opens = (commit["date"].date() + timedelta(days=21)).isoformat()
            if opens <= date_str:
                continue  # 该天视角下已到期的不补密封,不复活成洪流
            for idx, risk in enumerate(commit["narrative"]["risks"]):
                cache.seal_capsule(pkey, commit["sha"], idx, risk,
                                   sealed, opens)
        # 仅对真正的「今日」削峰(留次日);历史回放当天全开,天数不失真
        cap_limit = 3 if day == date.today() else None
        capsules = cache.open_due_capsules(pkey, date_str, cap_limit)
        on_this_day = {}
        for label, shifted in (("上月今日", _shift(day, months=1)),
                               ("去年今日", _shift(day, years=1))):
            past = cache.get_daily(pkey, shifted.isoformat())
            if past:
                on_this_day[label] = (shifted.isoformat(), past["overview"])
        hits = sum(1 for c in day_commits if c["sha"] in pre_cached)
        days.append({
            "date_str": date_str, "commits": day_commits, "overview": overview,
            "decision": decision, "capsules": capsules, "today": day,
            "on_this_day": on_this_day, "llm_calls": len(day_commits) - hits + calls,
            "cache_hits": hits,
        })

    opened, filled = cache.capsule_fill_stats(pkey)
    paths = []
    for d in days:
        run_stats = {
            "commits": len(d["commits"]), "sessions": len(session_list),
            "cache_hits": d["cache_hits"], "llm_calls": d["llm_calls"],
            "tokens_in": llm.stats["input_tokens"],
            "tokens_out": llm.stats["output_tokens"],
            "model": f"{cfg['provider']}/{cfg['model']}",
            "elapsed_s": round(time.time() - started, 1),
            "capsule_opened": opened, "capsule_filled": filled,
        }
        content = report.render(project, d["date_str"], d["overview"],
                                d["commits"], session_list, session_err,
                                run_stats, decision=d["decision"],
                                on_this_day=d["on_this_day"],
                                capsules=d["capsules"], today=d["today"])
        path = report.write_report(cfg["vault_path"], project, d["date_str"],
                                   content)
        paths.append(path)
        report.append_usage({"command": "digest", "project": str(project_path),
                             "since": args.since, "report": str(path),
                             **run_stats})
    cache.close()
    print(f"生成 {len(paths)} 份日报:")
    for p in paths:
        print(f"  {p}")
    return 0
