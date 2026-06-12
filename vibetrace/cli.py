"""vibetrace CLI — single command: digest."""
import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import align, enrich, gitlog, report, sessions
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
    date_str = datetime.now().strftime("%Y-%m-%d")

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
    stats = enrich.enrich_commits(commits, llm, cache, str(project_path))
    overview, extra_calls = enrich.make_overview(
        commits, llm, cache, str(project_path), date_str)

    run_stats = {
        "commits": len(commits), "sessions": len(session_list),
        "cache_hits": stats["cache_hits"],
        "llm_calls": stats["llm_calls"] + extra_calls,
        "enrich_failures": stats["failures"],
        "tokens_in": llm.stats["input_tokens"],
        "tokens_out": llm.stats["output_tokens"],
        "model": f"{cfg['provider']}/{cfg['model']}",
        "elapsed_s": round(time.time() - started, 1),
    }
    content = report.render(project, date_str, overview, commits,
                            session_list, session_err, run_stats)
    path = report.write_report(cfg["vault_path"], project, date_str, content)
    report.append_usage({"command": "digest", "project": str(project_path),
                         "since": args.since, "report": str(path), **run_stats})
    cache.close()
    print(f"日报已写入:{path}")
    print(f"commits {run_stats['commits']} | 缓存命中 {stats['cache_hits']} | "
          f"LLM 调用 {run_stats['llm_calls']} | 用时 {run_stats['elapsed_s']}s")
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
    args = parser.parse_args(argv)
    if args.command == "tunnel":
        from .tunnel import render_tunnel
        path, err = render_tunnel(args.project)
        if err:
            print(f"错误:{err}", file=sys.stderr)
            return 2
        print(f"隧道已写入:{path}")
        return 0
    return digest(args)
