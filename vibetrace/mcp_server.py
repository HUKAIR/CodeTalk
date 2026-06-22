"""vibetrace MCP server(纯 stdlib stdio,无 MCP SDK)。

把零-LLM 接地能力(ask / blame / graph)暴露成 MCP 工具,供 Claude Code / Cursor /
Windsurf 等客户端在 agent 工作流里直接调用。从 stdin 读换行分隔的 JSON-RPC 2.0、
向 stdout 写响应、所有日志只走 stderr。对照 MCP 规范 2025-11-25(stdio = 换行分隔
JSON-RPC,消息内不含换行,server 可写 stderr,stdout 仅含合法 MCP 消息)。

纪律(load-bearing):
- stdout 纯净:只调返回字符串的闭包(answer_question(...,as_json=True)、
  collect_segments+_format、build_graph_json),绝不调 ask.ask()/blame.blame()/
  build_graph(它们 print/写盘);logging 重定向 stderr;任何 print 走 stderr。
- 出口脱敏:成功文本统一过 redact_secrets 再放进 content(交 MCP 客户端=出本机)。
- 容错降级绝不崩:畸形 JSON / 未知 method / 工具内部异常 → JSON-RPC error 或
  isError:true,serve 循环不退出。
"""
import json
import logging
import sys
from pathlib import Path

from .ask import answer_question
from .blame import collect_segments, _format as _blame_format
from .cache import Cache
from .config import CACHE_DB_PATH, load_config, redact_secrets
from .graph import build_graph_json
from .llm import LLMClient, LLMError
from .search import topic_search

log = logging.getLogger("vibetrace")

SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2025-11-25"          # 服务端支持值;initialize 优先回显客户端值

_TOOLS = [
    {"name": "vibetrace_ask",
     "description": "就某段代码接地提问:接项目记忆(commit 叙事 + 决策面包屑)回答"
                    "『这段代码当初为什么这么写』。无 key 时降级为确定性检索结果。",
     "inputSchema": {"type": "object", "properties": {
         "target": {"type": "string",
                    "description": "文件或 文件:起-止,如 vibetrace/llm.py:72-78"},
         "question": {"type": "string", "description": "你的问题"},
         "project": {"type": "string", "description": "项目路径(默认当前目录)"}},
         "required": ["target", "question"]}},
    {"name": "vibetrace_blame",
     "description": "行级决策溯源(零 LLM,确定性罗列触达这些行的 commit 及其决策史)。",
     "inputSchema": {"type": "object", "properties": {
         "target": {"type": "string",
                    "description": "文件或 文件:起-止,如 vibetrace/llm.py:72-78"},
         "project": {"type": "string", "description": "项目路径(默认当前目录)"}},
         "required": ["target"]}},
    {"name": "vibetrace_graph",
     "description": "决策影响图(时间轴 DAG,零 LLM):哪个决策 commit 波及了后续哪些"
                    "改动。返回 {nodes, edges} 的 JSON。",
     "inputSchema": {"type": "object", "properties": {
         "project": {"type": "string", "description": "项目路径(默认当前目录)"}},
         "required": []}},
    {"name": "vibetrace_search",
     "description": "主题级『当初为什么』召回(零 LLM,确定性接地):不带文件目标,在整个"
                    "项目记忆里按关键词找相关 commit,返回真实 why/决策/原话锚点(不重述)。",
     "inputSchema": {"type": "object", "properties": {
         "question": {"type": "string", "description": "主题/关键词(需 ≥3 字符)"},
         "project": {"type": "string", "description": "项目路径(默认当前目录)"}},
         "required": ["question"]}},
]


def _err(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id,
            "error": {"code": code, "message": message}}


def _result(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _ok_content(text):
    return {"content": [{"type": "text", "text": redact_secrets(text)}],
            "isError": False}


def _err_content(text):
    # 错误内容同样出本机(交 MCP 客户端),与 _ok_content 同口径出口脱敏:
    # 异常原文可能含 git remote URL 内嵌 token 等 secret。
    return {"content": [{"type": "text", "text": redact_secrets(text)}],
            "isError": True}


def _project_path(arguments, default_project, stderr):
    pp = Path(arguments.get("project") or default_project).resolve()
    print(f"vibetrace mcp: tool on project {pp}", file=stderr)  # 审计行(stderr)
    return pp


def _call_tool(name, arguments, cache, cfg, llm, default_project, stderr):
    """dispatch 到三工具之一 → tools/call 的 result(content + isError)。
    校验工具名/参数齐全;整段包 try → isError:true,绝不崩循环。成功文本出口脱敏。"""
    if name not in {t["name"] for t in _TOOLS}:
        return _err_content(f"未知工具:{name}")
    if arguments is None:                   # MCP 协议 arguments 可选,缺省=空对象
        arguments = {}
    if not isinstance(arguments, dict):
        return _err_content("arguments 必须是对象(JSON object)")
    schema = next(t["inputSchema"] for t in _TOOLS if t["name"] == name)
    missing = [k for k in schema["required"] if not arguments.get(k)]
    if missing:
        return _err_content(f"缺少必填参数:{'、'.join(missing)}")
    try:
        pp = _project_path(arguments, default_project, stderr)
        if name == "vibetrace_ask":
            text, err = answer_question(
                cache, llm, pp, pp.name, arguments["target"],
                arguments["question"], as_json=True)
            if err:
                return _err_content(err)
            return _ok_content(text)
        if name == "vibetrace_blame":
            from .blame import _parse_target
            file, start, end = _parse_target(arguments["target"])
            segments = collect_segments(cache, pp, file, start, end)
            if not segments:
                return _err_content(f"{file} 没有可用的提交历史,无从溯源。")
            return _ok_content(_blame_format(file, start, end, segments))
        if name == "vibetrace_search":         # 主题级零-LLM 召回,出口同样脱敏
            return _ok_content(topic_search(cache, pp, arguments["question"]))
        # vibetrace_graph
        text, err = build_graph_json(pp, cache)
        if err:
            return _err_content(err)
        return _ok_content(text)
    except Exception as exc:               # 业务层任何异常 → isError,不崩循环
        log.warning("tool %s 调用失败:%s", name, exc)
        return _err_content(f"工具内部错误:{exc}")


def _handle(req, cache, cfg, llm, default_project=".", stderr=sys.stderr):
    """按 method 分发 → response | None(notification 无 id → 不回)。
    所有 error/result 透传 req.get('id')。"""
    req_id = req.get("id")
    method = req.get("method")
    if "id" not in req:                     # JSON-RPC 通知(无 id):任何 method 都不回、不执行请求型操作
        return None
    if method == "initialize":
        params = req.get("params") or {}
        return _result(req_id, {
            "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "vibetrace", "version": SERVER_VERSION}})
    if method == "ping":
        return _result(req_id, {})
    if method == "tools/list":
        return _result(req_id, {"tools": _TOOLS})
    if method == "tools/call":
        params = req.get("params") or {}
        result = _call_tool(params.get("name"), params.get("arguments"),
                            cache, cfg, llm, default_project, stderr)
        return _result(req_id, result)
    return _err(req_id, -32601, f"未知 method:{method}")


def serve(stdin, stdout, cache, cfg, llm, default_project=".", stderr=sys.stderr):
    """逐行读 JSON-RPC → json.loads(失败回 -32700 id=null)→ _handle → 写响应。
    数组(batch)→ -32600(不支持)。EOF 退出。stdout 仅含换行分隔的合法 MCP 消息。"""
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except (ValueError, TypeError):
            _write(stdout, _err(None, -32700, "Parse error"))
            continue
        if isinstance(req, list):          # batch 不支持
            _write(stdout, _err(None, -32600, "不支持批量请求(JSON 数组)"))
            continue
        if not isinstance(req, dict):
            _write(stdout, _err(None, -32600, "Invalid Request"))
            continue
        resp = _handle(req, cache, cfg, llm, default_project=default_project,
                       stderr=stderr)
        if resp is not None:
            _write(stdout, resp)


def _write(stdout, obj):
    stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    stdout.flush()


def run(project=None):
    """共用装配函数:cache/cfg/llm → serve(cli mcp-serve 与 -m 入口共用)。
    无 key → llm=None(ask 降级);stdout 重配 utf-8 保中文叙事;日志走 stderr。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    cfg = load_config()
    cache = Cache(CACHE_DB_PATH)
    try:
        llm = LLMClient(cfg)
    except LLMError:
        llm = None                         # 无 key → 降级,不报错退出
    print("vibetrace MCP server 已启动(stdio),等待 JSON-RPC……", file=sys.stderr)
    try:
        serve(sys.stdin, sys.stdout, cache, cfg, llm,
              default_project=project or ".")
    finally:
        cache.close()


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING,
                        format="vibetrace %(levelname)s: %(message)s")
    run()
