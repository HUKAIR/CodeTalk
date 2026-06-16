"""vibetrace CLI — single command: digest."""
import argparse
import calendar
import logging
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import align, brief, enrich, gitlog, report, sessions
from .cache import Cache
from .config import CACHE_DB_PATH, load_config
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
    started = time.time()
    cfg = load_config()
    if args.provider:
        cfg["provider"] = args.provider
    if args.model:
        cfg["model"] = args.model
    if args.vault:
        cfg["vault_path"] = args.vault
    project_path = Path(args.project).resolve()
    project = project_path.name

    commits, git_err = gitlog.collect_commits(
        project_path, args.since, cfg["diff_token_budget"])
    if git_err:
        print(f"错误:{git_err}", file=sys.stderr)
        return 2
    if not commits:
        print(f"{args.since} 以来没有 commit,无日报可写。")
        return 0

    cache = Cache(CACHE_DB_PATH)
    session_list, session_err = sessions.scan_sessions(
        project_path, _since_to_dt(args.since), cache)
    if session_err:
        log.warning("会话层降级:%s", session_err)
    align.align(commits, session_list, project_path)

    try:
        llm = LLMClient(cfg)
    except LLMError as exc:
        print(f"错误:{exc}", file=sys.stderr)
        return 2
    # 回读上次运行后用户在 Obsidian 里勾选的胶囊答案,闭合预测-验证环
    report.read_capsule_answers(cfg["vault_path"], project, cache)
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
        cache.put_daily(project, date_str, overview, decision)
        for commit in day_commits:  # 以该天为「今日」封存,忠实重放胶囊时间线
            sealed = commit["date"].date().isoformat()
            opens = (commit["date"].date() + timedelta(days=21)).isoformat()
            if opens <= date_str:
                continue  # 该天视角下已到期的不补密封,不复活成洪流
            for idx, risk in enumerate(commit["narrative"]["risks"]):
                cache.seal_capsule(project, commit["sha"], idx, risk,
                                   sealed, opens)
        capsules = cache.open_due_capsules(project, date_str)
        on_this_day = {}
        for label, shifted in (("上月今日", _shift(day, months=1)),
                               ("去年今日", _shift(day, years=1))):
            past = cache.get_daily(project, shifted.isoformat())
            if past:
                on_this_day[label] = (shifted.isoformat(), past["overview"])
        hits = sum(1 for c in day_commits if c["sha"] in pre_cached)
        days.append({
            "date_str": date_str, "commits": day_commits, "overview": overview,
            "decision": decision, "capsules": capsules, "today": day,
            "on_this_day": on_this_day, "llm_calls": len(day_commits) - hits + calls,
            "cache_hits": hits,
        })

    opened, filled = cache.capsule_fill_stats(project)
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


def brief_cmd(args):
    cfg = load_config()
    if args.vault:
        cfg["vault_path"] = args.vault
    project_path = Path(args.project).resolve()
    project = project_path.name
    cache = Cache(CACHE_DB_PATH)
    content = brief.build_brief(cache, project, str(project_path))
    cache.close()
    print(content)
    if args.vault:
        path = report.write_report(cfg["vault_path"], project, "brief", content)
        print(f"简报已写入:{path}")
    return 0


def main(argv=None):
    logging.basicConfig(level=logging.WARNING,
                        format="vibetrace %(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(
        prog="vibetrace", description="个人 AI 编码认知层:git+会话 → 变更叙事日报")
    sub = parser.add_subparsers(dest="command", required=True)
    dig = sub.add_parser("digest", help="生成开发日报")
    dig.add_argument("--project", default=".", help="项目路径(默认当前目录)")
    dig.add_argument("--since", default="1 day ago", help='如 "3 days ago"')
    dig.add_argument("--vault", help="覆盖日报输出目录")
    dig.add_argument("--provider", help="覆盖 LLM provider")
    dig.add_argument("--model", help="覆盖模型 ID")
    tun = sub.add_parser("tunnel", help="生成时光隧道(实验)")
    tun.add_argument("--project", default=".", help="项目路径(默认当前目录)")
    bri = sub.add_parser("brief", help="开工简报:你上次停在哪(纯本地,无 LLM)")
    bri.add_argument("--project", default=".", help="项目路径(默认当前目录)")
    bri.add_argument("--vault", help="同时写入该目录(默认仅打印)")
    args = parser.parse_args(argv)
    if args.command == "tunnel":
        from .tunnel import render_tunnel
        path, err = render_tunnel(args.project)
        if err:
            print(f"错误:{err}", file=sys.stderr)
            return 2
        print(f"隧道已写入:{path}")
        return 0
    if args.command == "brief":
        return brief_cmd(args)
    return digest(args)
