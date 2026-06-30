"""视图/输出类子命令——从 commands.py 拆出以守 300 行红线。"""
import sys
from pathlib import Path

from .cache import Cache
from .config import load_config
from .search import topic_search


def _cache_db_path():
    from . import cli
    return cli.CACHE_DB_PATH


def _fail(msg):
    print(f"错误:{msg}", file=sys.stderr)
    return 2


def _render_or_serve(args, render, serve, label):
    if args.serve:
        err = serve(args.project, open_browser=not args.no_open)
        return _fail(err) if err else 0
    path, err = render(args.project)
    if err: return _fail(err)
    print(f"{label}已写入:{path}")
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


def course_cmd(args):
    from .course import build_course
    path, err = build_course(args.project, no_llm=getattr(args, "no_llm", False))
    if err:
        return _fail(err)
    print(f"课程已写入:{path}")
    return 0


def graph_cmd(args):
    from .graph import build_graph
    path, err = build_graph(args.project, vault=args.vault, canvas=args.canvas)
    if err:
        return _fail(err)
    print(f"决策图已写入:{path}")
    return 0


def ask_cmd(args):
    from .ask import ask
    return ask(args.project, args.target, args.question, vault=args.vault,
               since=args.since, as_json=args.as_json,
               no_llm=getattr(args, "no_llm", False))


def blame_cmd(args):
    from .blame import blame
    return blame(args.project, args.target,
                 json_output=getattr(args, "as_json", False))


def review_cmd(args):
    """review 现场入口(零 LLM):--diff 文件 / 管道 stdin / 默认 git diff HEAD。"""
    from .review import review
    diff_text = None
    if getattr(args, "diff", None):
        try:
            diff_text = Path(args.diff).read_text(encoding="utf-8")
        except OSError as exc:
            return _fail(f"读 diff 文件失败:{exc}")
    elif not sys.stdin.isatty():
        diff_text = sys.stdin.read()
    out, err = review(args.project, diff_text)
    if err:
        return _fail(err)
    print(out)
    return 0


def search_cmd(args):
    """主题级零-LLM 召回:装配 cache → topic_search → 打印。无 key 也能用。"""
    pp = Path(args.project).resolve()
    cache = Cache(_cache_db_path())
    text = topic_search(cache, pp, args.question)
    cache.close()
    print(text)
    return 0


def prompts_cmd(args):
    """指令回看(零 LLM):scan 会话 → 本地 commit 软对齐 → 时间线视图。"""
    from . import align, gitlog
    from .prompts_view import build_prompts_view
    cfg = load_config()
    pp = Path(args.project).resolve()
    cache = Cache(_cache_db_path())
    cache.rekey_project(pp.name, str(pp))
    sess = _scan_sessions(cfg, args, pp, cache)
    commits, _err = gitlog.collect_commits(
        pp, args.since, cfg.get("diff_token_budget", 6000))
    align.align(commits or [], sess, pp)
    cache.close()
    print(build_prompts_view(sess, commits or [], pp))
    return 0


from .commands import _scan_sessions  # 单一来源,避免两份逻辑分叉


def web_cmd(args):
    """起自托管接地对话 web app(FastAPI,需 pip install -e \".[web]\")。绑 127.0.0.1。"""
    try:
        from . import web
    except ImportError:
        return _fail('web 模式需要额外依赖:pip install -e ".[web]"')
    web.serve(args.project, port=args.port, no_open=args.no_open, no_llm=args.no_llm)
    return 0


def mcp_serve_cmd(args):
    """起 MCP server(stdio)。阻塞至 EOF。"""
    from . import mcp_server
    mcp_server.run(args.project)
    return 0


def install_hook_cmd(args):
    from .hook import install_hook
    path, err = install_hook(args.project, force=args.force)
    if err:
        return _fail(err)
    print(f"钩子已装:{path}\n手写 commit 时会提示留 Vibe-Decision/Watch。")
    return 0


def install_agent_seed_cmd(args):
    from .hook import install_agent_seed
    paths, err = install_agent_seed(args.project)
    if err:
        return _fail(err)
    print("决策捕获种子已就绪:" + "、".join(str(p) for p in paths)
          + "\nAI agent 提交时会按约定留 Vibe-Decision/Watch,供 vibetrace 长期分析。")
    return 0
