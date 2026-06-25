"""vibetrace 子命令实现 — cli.py 负责解析/分发,这里负责各命令的逻辑。"""
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import brief, report
from .cache import Cache
from .config import USAGE_LOG_PATH, load_config
from .digest import digest  # noqa: F401 — cli._DISPATCH 经 commands.digest 分发
from .search import topic_search

log = logging.getLogger("vibetrace")


def _cache_db_path():
    # 经 cli 解析,让既有测试的 patch.object(cli, "CACHE_DB_PATH") 仍生效。
    from . import cli
    return cli.CACHE_DB_PATH


def _fail(msg):
    print(f"错误:{msg}", file=sys.stderr)
    return 2


def _render_or_serve(args, render, serve, label):  # tunnel/console 共用:serve 起服务,否则写静态
    if args.serve:
        err = serve(args.project, open_browser=not args.no_open)
        return _fail(err) if err else 0
    path, err = render(args.project)
    if err: return _fail(err)
    print(f"{label}已写入:{path}")
    return 0


def brief_cmd(args):
    cfg = load_config()
    if args.vault:
        cfg["vault_path"] = args.vault
    cache = Cache(_cache_db_path())
    if args.all:
        today = datetime.now(timezone.utc).astimezone().date()
        projects = cache.distinct_projects()
        content = brief.build_overview(cache, projects, today)
        cache.close()
        report.append_usage({"command": "brief", "mode": "all",
                             "projects": len(projects)})
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
    report.append_usage({"command": "brief", "mode": "single", "project": pkey})
    print(content)
    if args.vault:
        path = report.write_report(cfg["vault_path"], project, "brief", content)
        print(f"简报已写入:{path}")
    return 0


def watch_cmd(args):
    """跨项目 watch 收件箱:列出所有项目里已到期未回填的胶囊(零 LLM,不出网)。"""
    cfg = load_config()
    cache = Cache(_cache_db_path())
    today = datetime.now(timezone.utc).astimezone().date()
    content = brief.build_watch(cache, cache.distinct_projects(), today)
    cache.close()
    print(content)
    if args.vault:
        path = report.write_report(cfg["vault_path"], "watch", "watch", content)
        print(f"收件箱已写入:{path}")
    return 0


def self_cmd(args):
    """自我周报(零 LLM):解析 usage.log 聚合近 N 天用量,回填率取自全项目胶囊统计。"""
    from . import self_report
    cache = Cache(_cache_db_path())
    fill = self_report.aggregate_fill(cache)
    cache.close()
    print(self_report.build_self_report(USAGE_LOG_PATH, args.days, fill))
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


def enrich_cmd(args):
    """富集补全(coverage):给全史中尚无叙事的 commit 补叙事(跳过已缓存),不写日报、
    不封胶囊——闭合 search/blame/ask 召回覆盖缺口(digest 只富集 --since 窗口)。需 LLM。"""
    from . import align, enrich, gitlog
    from .llm import LLMClient, LLMError
    cfg = load_config()
    if getattr(args, "no_llm", False):
        cfg["no_llm"] = True
    pp = Path(args.project).resolve()
    commits, err = gitlog.collect_commits(pp, args.since, cfg["diff_token_budget"])
    if err:
        return _fail(err)
    align.align(commits, [], pp)            # 置齐 enrich 所需 commit 字段(无会话即空 evidence)
    cache = Cache(_cache_db_path())
    cache.rekey_project(pp.name, str(pp))   # 迁移旧 basename 键(幂等)
    missing = [c for c in commits if not cache.get_narrative(c["sha"])]
    if not missing:
        cache.close()
        print(f"全部 {len(commits)} 个 commit 已有叙事,无需补全。")
        return 0
    try:
        llm = LLMClient(cfg)
    except LLMError as exc:
        cache.close()
        return _fail(exc)        # 富集需 LLM:no_llm/无 key → 直接退出,不静默
    stats = enrich.enrich_commits(missing, llm, cache, str(pp))
    cache.close()
    print(f"补全 {len(missing)}/{len(commits)} 个无叙事 commit:"
          f"LLM {stats['llm_calls']} · 机械跳过 {stats['trivial']} · 失败 {stats['failures']}。")
    return 0


def course_cmd(args):
    from .course import build_course
    path, err = build_course(args.project, no_llm=getattr(args, "no_llm", False))
    if err:
        return _fail(err)
    print(f"课程已写入:{path}")
    return 0


def tunnel_cmd(args):
    from .tunnel import render_tunnel, serve_tunnel
    return _render_or_serve(args, render_tunnel, serve_tunnel, "时光轴")


def console_cmd(args):
    from .console import render_console, serve_console
    return _render_or_serve(args, render_console, serve_console, "控制台")


def report_cmd(args):
    from .briefing import render_report, serve_report
    return _render_or_serve(args, render_report, serve_report, "汇报")


def ask_cmd(args):
    from .ask import ask
    return ask(args.project, args.target, args.question, vault=args.vault,
               since=args.since, as_json=args.as_json,
               no_llm=getattr(args, "no_llm", False))


def blame_cmd(args):
    from .blame import blame
    return blame(args.project, args.target)


def search_cmd(args):
    """主题级零-LLM 召回:装配 cache → topic_search → 打印。无 key 也能用。"""
    pp = Path(args.project).resolve()
    cache = Cache(_cache_db_path())
    text = topic_search(cache, pp, args.question)
    cache.close()
    print(text)
    return 0


def prompts_cmd(args):
    """指令回看(零 LLM):scan 会话 → 本地 commit 软对齐 → 时间线视图。无 key 也能用、不出网。"""
    from . import align, cursor_sessions, gitlog, sessions
    from .digest import _since_to_dt, _sources
    from .prompts_view import build_prompts_view
    cfg = load_config()
    pp = Path(args.project).resolve()
    since_dt = _since_to_dt(args.since)
    cache = Cache(_cache_db_path())
    cache.rekey_project(pp.name, str(pp))   # 迁移旧 basename 键(幂等)
    srcs = _sources(cfg, args)
    sess = []
    if "claude" in srcs:
        s_list, s_err = sessions.scan_sessions(pp, since_dt, cache)
        if s_err:
            log.warning("会话层降级:%s", s_err)
        sess += s_list
    if "cursor" in srcs:
        cursor_sessions.maybe_notice()
        c_list, c_err = cursor_sessions.scan_sessions(pp, since_dt, cache)
        if c_err:
            log.warning("Cursor 会话层降级:%s", c_err)
        sess += c_list
    commits, _err = gitlog.collect_commits(
        pp, args.since, cfg.get("diff_token_budget", 6000))  # 本地 git,不出网
    align.align(commits or [], sess, pp)
    cache.close()
    print(build_prompts_view(sess, commits or [], pp))
    return 0


def graph_cmd(args):
    from .graph import build_graph
    path, err = build_graph(args.project, vault=args.vault, canvas=args.canvas)
    if err:
        return _fail(err)
    print(f"决策图已写入:{path}")
    return 0


def install_hook_cmd(args):
    from .hook import install_hook
    path, err = install_hook(args.project, force=args.force)
    if err:
        return _fail(err)
    print(f"钩子已装:{path}\n手写 commit 时会提示留 Vibe-Decision/Watch。")
    return 0


def web_cmd(args):
    """起自托管接地对话 web app(FastAPI,需 pip install -e \".[web]\")。绑 127.0.0.1。"""
    try:
        from . import web
    except ImportError:
        return _fail('web 模式需要额外依赖:pip install -e ".[web]"')
    web.serve(args.project, port=args.port, no_open=args.no_open, no_llm=args.no_llm)
    return 0


def mcp_serve_cmd(args):
    """起 MCP server(stdio):共用 mcp_server.run 装配 cache/cfg/llm。阻塞至 EOF。"""
    from . import mcp_server
    mcp_server.run(args.project)
    return 0


def install_agent_seed_cmd(args):
    from .hook import install_agent_seed
    paths, err = install_agent_seed(args.project)
    if err:
        return _fail(err)
    print("决策捕获种子已就绪:" + "、".join(str(p) for p in paths)
          + "\nAI agent 提交时会按约定留 Vibe-Decision/Watch,供 vibetrace 长期分析。")
    return 0
