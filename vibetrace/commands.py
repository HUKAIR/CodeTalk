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


def course_cmd(args):
    from .course import build_course
    path, err = build_course(args.project)
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


def ask_cmd(args):
    from .ask import ask
    return ask(args.project, args.target, args.question, vault=args.vault,
               since=args.since, as_json=args.as_json)


def blame_cmd(args):
    from .blame import blame
    return blame(args.project, args.target)


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
