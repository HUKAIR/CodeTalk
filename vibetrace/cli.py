"""vibetrace CLI — 解析参数并分发到 commands.py 的各子命令实现。"""
import argparse
import logging

from . import commands
from .config import CACHE_DB_PATH  # commands 经 cli 读取它,沿用既有测试 patch 目标


def _proj(p):  # 折叠各子命令重复的 --project
    p.add_argument("--project", default=".", help="项目路径(默认当前目录)"); return p


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="vibetrace", description="个人 AI 编码认知层:git+会话 → 变更叙事日报")
    sub = parser.add_subparsers(dest="command", required=True)
    dig = _proj(sub.add_parser("digest", help="生成开发日报"))
    dig.add_argument("--since", default="1 day ago", help='如 "3 days ago"')
    dig.add_argument("--vault", help="覆盖日报输出目录")
    dig.add_argument("--provider", help="覆盖 LLM provider")
    dig.add_argument("--model", help="覆盖模型 ID")
    dig.add_argument("--source", choices=["claude", "cursor", "both"],
                     help="会话源(默认按 config.sources;cursor 需 opt-in)")
    dig.add_argument("--with-pr", action="store_true",
                     help="额外用 GitHub PR 讨论作 why 源(数据出本机,opt-in)")
    dig.add_argument("--no-llm", action="store_true",
                     help="显式关闭 LLM(数据不出本机);digest 需 LLM 故会直接退出")
    tun = _proj(sub.add_parser("tunnel", help="生成时光轴(线性时间线)"))
    tun.add_argument("--serve", action="store_true",
                     help="起本地服务,胶囊回答即时写回 cache(否则只读)")
    tun.add_argument("--no-open", action="store_true", help="--serve 时不自动开浏览器")
    bri = _proj(sub.add_parser("brief", help="开工简报:你上次停在哪(纯本地,无 LLM)"))
    bri.add_argument("--vault", help="同时写入该目录(默认仅打印)")
    bri.add_argument("--all", action="store_true",
                     help="跨项目总览:所有项目里需要注意的(零 LLM,忽略 --project)")
    wat = sub.add_parser(
        "watch", help="待验证收件箱:跨项目列出到期未回填的预测(零 LLM)")
    wat.add_argument("--vault", help="同时写入该目录(默认仅打印)")
    slf = sub.add_parser(
        "self", help="自我周报:近 N 天用量/省额/回填率,自证关掉 LLM 仍有价值(零 LLM)")
    slf.add_argument("--days", type=int, default=7, help="聚合窗口天数(默认 7)")
    enr = _proj(sub.add_parser(
        "enrich", help="富集补全:给全史中尚无叙事的 commit 补叙事(闭合召回覆盖,需 LLM)"))
    enr.add_argument("--since", default="20 years ago",
                     help='富集范围(默认全史;如 "3 months ago")')
    enr.add_argument("--no-llm", action="store_true",
                     help="显式关闭 LLM(仍做零-LLM 的 evidence 补;未叙事项跳过)")
    enr.add_argument("--source", choices=["claude", "cursor", "both"],
                     help="会话源(默认按 config.sources;影响 evidence 原话锚点收割)")
    crs = _proj(sub.add_parser("course", help="生成演进课程(项目怎么长成的,实验)"))
    crs.add_argument("--no-llm", action="store_true",
                     help="显式关闭 LLM(数据不出本机);降级为按时间均分的朴素课程")
    asq = _proj(sub.add_parser("ask", help="就某段代码提问(接项目记忆,接地回答)"))
    asq.add_argument("target", help='文件或 文件:起-止,如 vibetrace/llm.py:72-78')
    asq.add_argument("question", help="你的问题")
    asq.add_argument("--vault", help="同时写一份脱敏 Q&A 笔记到该目录")
    asq.add_argument("--since", help='时间范围:日期(如 "3 days ago"/2026-06-18)'
                     "或 commit 范围(如 abc..def);把检索从空间叠到时间维度")
    asq.add_argument("--json", action="store_true", dest="as_json",
                     help="结构化 JSON 输出(agent 可读;无 key 时给确定性检索结果)")
    asq.add_argument("--no-llm", action="store_true",
                     help="显式关闭 LLM(数据不出本机);降级为确定性检索结果")
    blm = _proj(sub.add_parser("blame",
                               help="行级决策溯源(零 LLM,确定性罗列,无 key 也能用)"))
    blm.add_argument("target", help='文件或 文件:起-止,如 vibetrace/llm.py:72-78')
    rev = _proj(sub.add_parser(
        "review", help="review 现场:粘 diff/git diff → 逐改动块的历史决策+真实引用(零 LLM)"))
    rev.add_argument("--diff", help="读 diff 文件(默认 git diff HEAD;或 git diff | vibetrace review)")
    sea = _proj(sub.add_parser(
        "search", help="主题级『当初为什么』召回:全仓按关键词找相关 commit(零 LLM)"))
    sea.add_argument("question", help="主题/关键词(需 ≥3 字符)")
    prm = _proj(sub.add_parser(
        "prompts",
        help="指令回看:按会话时间线列出你发给 AI 的指令 + 改过的文件(零 LLM)"))
    prm.add_argument("--since", default="1 day ago",
                     help='如 "3 days ago"/2026-06-20(默认近 1 天)')
    prm.add_argument("--source", choices=["claude", "cursor", "both"],
                     help="会话源(默认按 config.sources;cursor 需 opt-in)")
    grp = _proj(sub.add_parser("graph", help="生成决策影响图(时间轴 DAG,零 LLM)"))
    grp.add_argument("--vault", help="覆盖输出目录")
    grp.add_argument("--canvas", action="store_true",
                     help="额外导出 Obsidian JSON Canvas(*-graph.canvas)")
    con = _proj(sub.add_parser("console", help="统一控制台:四视图单页 web(零 LLM)"))
    con.add_argument("--serve", action="store_true", help="起本地服务,回答写回 cache")
    con.add_argument("--no-open", action="store_true", help="--serve 时不自动开浏览器")
    rep = _proj(sub.add_parser(
        "report", help="实时汇报:从当前仓状态生成单页 web(变更/面包屑/发现,零 LLM)"))
    rep.add_argument("--serve", action="store_true",
                     help="起本地服务并自动开浏览器(否则写静态 HTML)")
    rep.add_argument("--no-open", action="store_true", help="--serve 时不自动开浏览器")
    web = _proj(sub.add_parser(
        "web", help="自托管接地对话 web app(FastAPI,需 .[web];绑 127.0.0.1)"))
    web.add_argument("--port", type=int, default=8000, help="端口(默认 8000)")
    web.add_argument("--no-open", action="store_true", help="不自动开浏览器")
    web.add_argument("--no-llm", action="store_true",
                     help="显式关闭 LLM(对话降级为零-LLM 接地罗列,数据不出本机)")
    ini = sub.add_parser("init", help="生成配置模板到 ~/.vibetrace/config.json")
    ini.add_argument("--force", action="store_true", help="已存在时覆盖")
    ihk = _proj(sub.add_parser("install-hook",
                               help="装 git 钩子:手写 commit 时提示留决策面包屑"))
    ihk.add_argument("--force", action="store_true", help="覆盖已有钩子")
    _proj(sub.add_parser(
        "install-agent-seed",
        help="把决策捕获约定植入项目 CLAUDE.md,让 AI agent 提交时留推导面包屑"))
    _proj(sub.add_parser(
        "mcp-serve",
        help="起 MCP server(stdio):把 ask/blame/graph 暴露给 MCP 客户端(零 LLM 接地)"))
    return parser


# 子命令名 → commands.py 中的处理函数(add_subparsers required=True,必命中)。
_DISPATCH = {
    "digest": commands.digest,
    "tunnel": commands.tunnel_cmd,
    "console": commands.console_cmd,
    "report": commands.report_cmd,
    "brief": commands.brief_cmd,
    "watch": commands.watch_cmd,
    "self": commands.self_cmd,
    "ask": commands.ask_cmd,
    "blame": commands.blame_cmd,
    "review": commands.review_cmd,
    "search": commands.search_cmd,
    "prompts": commands.prompts_cmd,
    "graph": commands.graph_cmd,
    "course": commands.course_cmd,
    "enrich": commands.enrich_cmd,
    "init": commands.init_cmd,
    "install-hook": commands.install_hook_cmd,
    "install-agent-seed": commands.install_agent_seed_cmd,
    "mcp-serve": commands.mcp_serve_cmd,
    "web": commands.web_cmd,
}


def main(argv=None):
    logging.basicConfig(level=logging.WARNING,
                        format="vibetrace %(levelname)s: %(message)s")
    args = _build_parser().parse_args(argv)
    return _DISPATCH[args.command](args)
