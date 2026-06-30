"""MCP tool definitions + dispatch (从 mcp_server.py 拆出,守 300 行红线)。

TOOLS 列表 + call_tool dispatch + target/project 解析 + content helpers。
mcp_server.py 只留 JSON-RPC serve loop + run()。
"""
import json
import logging
from pathlib import Path

from .adr_export import export as adr_export
from .ask import answer_question
from .blame import collect_segments, _format as _blame_format
from .config import redact_secrets
from .drift import drift_json
from .graph import build_graph_json
from .prompts_view import build_prompts_view
from .search import topic_search

log = logging.getLogger("vibetrace")

TOOLS = [
    {"name": "vibetrace_ask",
     "description":
         "Grounded code Q&A: answer 'why was this code written this way' using real commit "
         "narratives and decision breadcrumbs (verbatim citations with SHA). Falls back to "
         "deterministic retrieval when no LLM key is configured.",
     "inputSchema": {"type": "object", "properties": {
         "target": {"type": "string",
                    "description": "File or file:start-end, e.g. vibetrace/llm.py:72-78"},
         "path": {"type": "string", "description": "GitHub-MCP style file path (alias for target)"},
         "startLine": {"type": "integer", "description": "Start line (with path)"},
         "endLine": {"type": "integer", "description": "End line (with path)"},
         "question": {"type": "string", "description": "Your question about the code"},
         "project": {"type": "string", "description": "Project path (default: cwd)"}},
         "required": ["question"]},
     "annotations": {"title": "vibetrace ask", "readOnlyHint": True,
                     "destructiveHint": False, "openWorldHint": False}},

    {"name": "vibetrace_blame",
     "description":
         "Line-level decision provenance (zero-LLM, deterministic). Lists every commit that "
         "touched these lines with its real decisions, why, and verbatim citations. Use during "
         "code review to understand 'why was this written this way' with ground-truth evidence.",
     "inputSchema": {"type": "object", "properties": {
         "target": {"type": "string",
                    "description": "File or file:start-end, e.g. vibetrace/llm.py:72-78"},
         "path": {"type": "string", "description": "GitHub-MCP style file path (alias for target)"},
         "startLine": {"type": "integer", "description": "Start line (with path)"},
         "endLine": {"type": "integer", "description": "End line (with path)"},
         "project": {"type": "string", "description": "Project path (default: cwd)"}},
         "required": []},
     "annotations": {"title": "vibetrace blame", "readOnlyHint": True,
                     "destructiveHint": False, "openWorldHint": False}},

    {"name": "vibetrace_graph",
     "description":
         "Decision impact graph (timeline DAG, zero-LLM): which decision commits rippled into "
         "subsequent changes. Returns {nodes, edges} JSON.",
     "inputSchema": {"type": "object", "properties": {
         "project": {"type": "string", "description": "Project path (default: cwd)"}},
         "required": []},
     "annotations": {"title": "vibetrace graph", "readOnlyHint": True,
                     "destructiveHint": False, "openWorldHint": False}},

    {"name": "vibetrace_search",
     "description":
         "Topic-level 'why' recall (zero-LLM, deterministic): search the entire project memory "
         "by keyword, returns real why/decisions/verbatim citations from matching commits. "
         "Use when reviewing or debugging to find related past decisions.",
     "inputSchema": {"type": "object", "properties": {
         "question": {"type": "string",
                      "description": "Topic or keyword (minimum 3 characters)"},
         "project": {"type": "string", "description": "Project path (default: cwd)"}},
         "required": ["question"]},
     "annotations": {"title": "vibetrace search", "readOnlyHint": True,
                     "destructiveHint": False, "openWorldHint": False}},

    {"name": "vibetrace_drift",
     "description":
         "Deviation report: AI tool actions vs actual git commits (zero-LLM, deterministic). "
         "Shows files the AI edited but never committed — catches 'said but didn't do'.",
     "inputSchema": {"type": "object", "properties": {
         "since": {"type": "string",
                   "description": "Time window, e.g. '7 days ago' (default)"},
         "project": {"type": "string", "description": "Project path (default: cwd)"}},
         "required": []},
     "annotations": {"title": "vibetrace drift", "readOnlyHint": True,
                     "destructiveHint": False, "openWorldHint": False}},

    {"name": "vibetrace_prompts",
     "description":
         "Replay your prompts to AI coding agents (zero-LLM, local-only). Shows what you "
         "asked the AI to do, with soft-aligned commits. Use when you forgot what you told "
         "the AI earlier today.",
     "inputSchema": {"type": "object", "properties": {
         "since": {"type": "string",
                   "description": "Time window, e.g. '1 day ago' (default: '7 days ago')"},
         "project": {"type": "string", "description": "Project path (default: cwd)"}},
         "required": []},
     "annotations": {"title": "vibetrace prompts", "readOnlyHint": True,
                     "destructiveHint": False, "openWorldHint": False}},

    {"name": "vibetrace_adr",
     "description":
         "Export an Architecture Decision Record from real git history (zero-LLM). "
         "Auto-generates MADR or Nygard ADR with verbatim commit citations for a file or "
         "line range. Must provide target or path.",
     "inputSchema": {"type": "object", "properties": {
         "target": {"type": "string",
                    "description": "File or file:start-end, e.g. vibetrace/llm.py:72-78"},
         "path": {"type": "string", "description": "GitHub-MCP style file path (alias for target)"},
         "startLine": {"type": "integer", "description": "Start line (with path)"},
         "endLine": {"type": "integer", "description": "End line (with path)"},
         "format": {"type": "string", "enum": ["madr", "nygard", "cyclonedx"],
                    "description": "ADR format (default: madr)"},
         "project": {"type": "string", "description": "Project path (default: cwd)"}},
         "required": []},
     "annotations": {"title": "vibetrace adr", "readOnlyHint": True,
                     "destructiveHint": False, "openWorldHint": False}},
]


def _ok_content(text):
    return {"content": [{"type": "text", "text": redact_secrets(text)}],
            "isError": False}


def _err_content(text):
    return {"content": [{"type": "text", "text": redact_secrets(text)}],
            "isError": True}


def project_path(arguments, default_project, stderr):
    pp = Path(arguments.get("project") or default_project).resolve()
    print(f"vibetrace mcp: tool on project {pp}", file=stderr)
    return pp


def resolve_target(arguments):
    """target directly given → use it; else build from GitHub-MCP style path[+startLine/endLine].
    owner/repo etc. are silently ignored (only .get the keys we need)."""
    if arguments.get("target"):
        return arguments["target"]
    path = arguments.get("path")
    if not path:
        return None
    start, end = arguments.get("startLine"), arguments.get("endLine")
    return f"{path}:{start}-{end}" if start and end else path


def call_tool(name, arguments, cache, cfg, llm, default_project, stderr):
    """Dispatch to the named tool → tools/call result (content + isError).
    Validates tool name and required params; wraps all exceptions → isError:true."""
    if name not in {t["name"] for t in TOOLS}:
        return _err_content(f"Unknown tool: {name}")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return _err_content("arguments must be a JSON object")
    schema = next(t["inputSchema"] for t in TOOLS if t["name"] == name)
    missing = [k for k in schema["required"] if not arguments.get(k)]
    if missing:
        return _err_content(f"Missing required parameter(s): {', '.join(missing)}")
    try:
        pp = project_path(arguments, default_project, stderr)
        if name == "vibetrace_ask":
            target = resolve_target(arguments)
            if not target:
                return _err_content("Missing target (or path[+startLine/endLine])")
            text, err = answer_question(
                cache, llm, pp, pp.name, target,
                arguments["question"], as_json=True)
            if err:
                return _err_content(err)
            return _ok_content(text)
        if name == "vibetrace_blame":
            from .blame import _parse_target
            target = resolve_target(arguments)
            if not target:
                return _err_content("Missing target (or path[+startLine/endLine])")
            file, start, end = _parse_target(target)
            segments = collect_segments(cache, pp, file, start, end)
            if not segments:
                return _err_content(f"No commit history for {file}")
            return _ok_content(_blame_format(file, start, end, segments))
        if name == "vibetrace_search":
            return _ok_content(topic_search(cache, pp, arguments["question"]))
        if name == "vibetrace_graph":
            text, err = build_graph_json(pp, cache)
            if err:
                return _err_content(err)
            return _ok_content(text)
        if name == "vibetrace_drift":
            return _ok_content(drift_json(
                str(pp), arguments.get("since", "7 days ago")))
        if name == "vibetrace_prompts":
            from . import sessions as sess_mod, gitlog as gl_mod
            from .align import align
            from .digest import _since_to_dt
            since_dt = _since_to_dt(arguments.get("since", "7 days ago"))
            sess, _ = sess_mod.scan_sessions(pp, since_dt, cache)
            commits, _ = gl_mod.collect_commit_files(pp)
            align(commits, sess, pp)
            return _ok_content(build_prompts_view(sess, commits, pp))
        if name == "vibetrace_adr":
            target = resolve_target(arguments)
            if not target:
                return _err_content("Missing target (or path[+startLine/endLine])")
            fmt = arguments.get("format", "madr")
            text, err = adr_export(str(pp), target, fmt=fmt)
            if err:
                return _err_content(err)
            return _ok_content(text)
        return _err_content(f"Unknown tool: {name}")
    except Exception as exc:
        log.warning("tool %s call failed: %s", name, exc)
        return _err_content(f"Internal tool error: {exc}")
