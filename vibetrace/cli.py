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
    _proj(sub.add_parser("course", help="生成演进课程(项目怎么长成的,实验)"))
    asq = _proj(sub.add_parser("ask", help="就某段代码提问(接项目记忆,接地回答)"))
    asq.add_argument("target", help='文件或 文件:起-止,如 vibetrace/llm.py:72-78')
    asq.add_argument("question", help="你的问题")
    asq.add_argument("--vault", help="同时写一份脱敏 Q&A 笔记到该目录")
    asq.add_argument("--since", help='时间范围:日期(如 "3 days ago"/2026-06-18)'
                     "或 commit 范围(如 abc..def);把检索从空间叠到时间维度")
    asq.add_argument("--json", action="store_true", dest="as_json",
                     help="结构化 JSON 输出(agent 可读;无 key 时给确定性检索结果)")
    blm = _proj(sub.add_parser("blame",
                               help="行级决策溯源(零 LLM,确定性罗列,无 key 也能用)"))
    blm.add_argument("target", help='文件或 文件:起-止,如 vibetrace/llm.py:72-78')
    grp = _proj(sub.add_parser("graph", help="生成决策影响图(时间轴 DAG,零 LLM)"))
    grp.add_argument("--vault", help="覆盖输出目录")
    grp.add_argument("--canvas", action="store_true",
                     help="额外导出 Obsidian JSON Canvas(*-graph.canvas)")
    con = _proj(sub.add_parser("console", help="统一控制台:四视图单页 web(零 LLM)"))
    con.add_argument("--serve", action="store_true", help="起本地服务,回答写回 cache")
    con.add_argument("--no-open", action="store_true", help="--serve 时不自动开浏览器")
    ini = sub.add_parser("init", help="生成配置模板到 ~/.vibetrace/config.json")
    ini.add_argument("--force", action="store_true", help="已存在时覆盖")
    ihk = _proj(sub.add_parser("install-hook",
                               help="装 git 钩子:手写 commit 时提示留决策面包屑"))
    ihk.add_argument("--force", action="store_true", help="覆盖已有钩子")
    _proj(sub.add_parser(
        "install-agent-seed",
        help="把决策捕获约定植入项目 CLAUDE.md,让 AI agent 提交时留推导面包屑"))
    return parser


# 子命令名 → commands.py 中的处理函数;digest 为默认(未匹配时兜底)。
_DISPATCH = {
    "digest": commands.digest,
    "tunnel": commands.tunnel_cmd,
    "console": commands.console_cmd,
    "brief": commands.brief_cmd,
    "watch": commands.watch_cmd,
    "self": commands.self_cmd,
    "ask": commands.ask_cmd,
    "blame": commands.blame_cmd,
    "graph": commands.graph_cmd,
    "course": commands.course_cmd,
    "init": commands.init_cmd,
    "install-hook": commands.install_hook_cmd,
    "install-agent-seed": commands.install_agent_seed_cmd,
}


def main(argv=None):
    logging.basicConfig(level=logging.WARNING,
                        format="vibetrace %(levelname)s: %(message)s")
    args = _build_parser().parse_args(argv)
    return _DISPATCH.get(args.command, commands.digest)(args)
