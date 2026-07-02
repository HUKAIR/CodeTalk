"""codetalk MCP server (pure stdlib stdio, no MCP SDK).

Thin JSON-RPC 2.0 serve loop. Tool definitions + dispatch live in mcp_tools.py.
Reads newline-delimited JSON-RPC from stdin, writes responses to stdout,
all logs go to stderr only. MCP spec 2025-11-25.

Discipline (load-bearing):
- stdout pure: only valid MCP JSON-RPC messages, one per line.
- Exit redaction: all tool output goes through mcp_tools._ok_content/_err_content.
- Graceful degradation: malformed JSON / unknown method / tool exceptions → JSON-RPC
  error or isError:true, serve loop never exits.
"""
import json
import logging
import sys

from . import __version__
from .cache import Cache
from .config import CACHE_DB_PATH, load_config
from .llm import LLMClient, LLMError
from .mcp_tools import TOOLS, call_tool

log = logging.getLogger("codetalk")

SERVER_VERSION = __version__        # 单一真源:包版本(pyproject),避免手工同步漂移
PROTOCOL_VERSION = "2025-11-25"


def _err(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id,
            "error": {"code": code, "message": message}}


def _result(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


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
            "serverInfo": {"name": "codetalk", "version": SERVER_VERSION}})
    if method == "ping":
        return _result(req_id, {})
    if method == "tools/list":
        return _result(req_id, {"tools": TOOLS})
    if method == "tools/call":
        params = req.get("params") or {}
        result = call_tool(params.get("name"), params.get("arguments"),
                           cache, cfg, llm, default_project, stderr)
        return _result(req_id, result)
    return _err(req_id, -32601, f"Unknown method: {method}")


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
            _write(stdout, _err(None, -32600, "Batch requests (JSON arrays) not supported"))
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
    print("codetalk MCP server 已启动(stdio),等待 JSON-RPC……", file=sys.stderr)
    try:
        serve(sys.stdin, sys.stdout, cache, cfg, llm,
              default_project=project or ".")
    finally:
        cache.close()


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING,
                        format="codetalk %(levelname)s: %(message)s")
    run()
