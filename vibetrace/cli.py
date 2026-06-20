"""vibetrace CLI — single command: digest."""
import argparse
import calendar
import json
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
    project = project_path.name        # 显示标题 / 输出文件名
    pkey = str(project_path)            # cache 键:绝对路径,同名项目不串

    commits, git_err = gitlog.collect_commits(
        project_path, args.since, cfg["diff_token_budget"])
    if git_err:
        print(f"错误:{git_err}", file=sys.stderr)
        return 2
    if not commits:
        print(f"{args.since} 以来没有 commit,无日报可写。")
        return 0

    cache = Cache(CACHE_DB_PATH)
    cache.rekey_project(project, pkey)   # 迁移旧 basename 键数据(一次性,幂等)
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


def brief_cmd(args):
    cfg = load_config()
    if args.vault:
        cfg["vault_path"] = args.vault
    cache = Cache(CACHE_DB_PATH)
    if args.all:
        today = datetime.now(timezone.utc).astimezone().date()
        content = brief.build_overview(cache, cache.distinct_projects(), today)
        cache.close()
        print(content)
        if args.vault:
            path = report.write_report(cfg["vault_path"], "overview",
                                       "brief", content)
            print(f"总览已写入:{path}")
        return 0
    project_path = Path(args.project).resolve()
    project = project_path.name
    pkey = str(project_path)
    cache.rekey_project(project, pkey)   # 迁移旧 basename 键数据(幂等)
    # 与 digest 对齐:先回读 Obsidian 里勾选的答案,否则简报会反复催问已答胶囊
    report.read_capsule_answers(cfg["vault_path"], pkey, cache)
    content = brief.build_brief(cache, project, pkey)
    cache.close()
    print(content)
    if args.vault:
        path = report.write_report(cfg["vault_path"], project, "brief", content)
        print(f"简报已写入:{path}")
    return 0


def init_cmd(args):
    """写配置模板到 ~/.vibetrace/config.json(chmod 600),引导填 key。"""
    from .config import CONFIG_PATH, DEFAULTS
    if CONFIG_PATH.exists() and not args.force:
        print(f"配置已存在:{CONFIG_PATH}(加 --force 覆盖)")
        return 0
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(DEFAULTS, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        CONFIG_PATH.chmod(0o600)  # 隐私:配置含 key,仅本人可读
    except OSError:
        pass
    print(f"已写入配置模板:{CONFIG_PATH}")
    print(f"请填 providers.{DEFAULTS['provider']}.api_key,"
          f"或设环境变量 {DEFAULTS['provider'].upper()}_API_KEY")
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
    tun.add_argument("--serve", action="store_true",
                     help="起本地服务,胶囊回答即时写回 cache(否则只读)")
    tun.add_argument("--no-open", action="store_true", help="--serve 时不自动开浏览器")
    bri = sub.add_parser("brief", help="开工简报:你上次停在哪(纯本地,无 LLM)")
    bri.add_argument("--project", default=".", help="项目路径(默认当前目录)")
    bri.add_argument("--vault", help="同时写入该目录(默认仅打印)")
    bri.add_argument("--all", action="store_true",
                     help="跨项目总览:所有项目里需要注意的(零 LLM,忽略 --project)")
    crs = sub.add_parser("course", help="生成演进课程(项目怎么长成的,实验)")
    crs.add_argument("--project", default=".", help="项目路径(默认当前目录)")
    asq = sub.add_parser("ask", help="就某段代码提问(接项目记忆,接地回答)")
    asq.add_argument("--project", default=".", help="项目路径(默认当前目录)")
    asq.add_argument("target", help='文件或 文件:起-止,如 vibetrace/llm.py:72-78')
    asq.add_argument("question", help="你的问题")
    asq.add_argument("--vault", help="同时写一份脱敏 Q&A 笔记到该目录")
    grp = sub.add_parser("graph", help="生成决策影响图(时间轴 DAG,零 LLM)")
    grp.add_argument("--project", default=".", help="项目路径(默认当前目录)")
    grp.add_argument("--vault", help="覆盖输出目录")
    grp.add_argument("--canvas", action="store_true",
                     help="额外导出 Obsidian JSON Canvas(*-graph.canvas)")
    ini = sub.add_parser("init", help="生成配置模板到 ~/.vibetrace/config.json")
    ini.add_argument("--force", action="store_true", help="已存在时覆盖")
    ihk = sub.add_parser("install-hook",
                         help="装 git 钩子:手写 commit 时提示留决策面包屑")
    ihk.add_argument("--project", default=".", help="项目路径(默认当前目录)")
    ihk.add_argument("--force", action="store_true", help="覆盖已有钩子")
    ias = sub.add_parser(
        "install-agent-seed",
        help="把决策捕获约定植入项目 CLAUDE.md,让 AI agent 提交时留推导面包屑")
    ias.add_argument("--project", default=".", help="项目路径(默认当前目录)")
    args = parser.parse_args(argv)
    if args.command == "course":
        from .course import build_course
        path, err = build_course(args.project)
        if err:
            print(f"错误:{err}", file=sys.stderr)
            return 2
        print(f"课程已写入:{path}")
        return 0
    if args.command == "tunnel":
        if args.serve:
            from .tunnel import serve_tunnel
            err = serve_tunnel(args.project, open_browser=not args.no_open)
            if err:
                print(f"错误:{err}", file=sys.stderr)
                return 2
            return 0
        from .tunnel import render_tunnel
        path, err = render_tunnel(args.project)
        if err:
            print(f"错误:{err}", file=sys.stderr)
            return 2
        print(f"隧道已写入:{path}")
        return 0
    if args.command == "brief":
        return brief_cmd(args)
    if args.command == "ask":
        from .ask import ask
        return ask(args.project, args.target, args.question, vault=args.vault)
    if args.command == "graph":
        from .graph import build_graph
        path, err = build_graph(args.project, vault=args.vault,
                                canvas=args.canvas)
        if err:
            print(f"错误:{err}", file=sys.stderr)
            return 2
        print(f"决策图已写入:{path}")
        return 0
    if args.command == "install-hook":
        from .hook import install_hook
        path, err = install_hook(args.project, force=args.force)
        if err:
            print(f"错误:{err}", file=sys.stderr)
            return 2
        print(f"钩子已装:{path}\n手写 commit 时会提示留 Vibe-Decision/Watch。")
        return 0
    if args.command == "install-agent-seed":
        from .hook import install_agent_seed
        path, err = install_agent_seed(args.project)
        if err:
            print(f"错误:{err}", file=sys.stderr)
            return 2
        print(f"决策捕获种子已就绪:{path}\n"
              "AI agent 提交时会按约定留 Vibe-Decision/Watch,供 vibetrace 长期分析。")
        return 0
    if args.command == "init":
        return init_cmd(args)
    return digest(args)
