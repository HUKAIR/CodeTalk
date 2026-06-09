"""Tolerant parser for Claude Code session JSONL (non-official format).

Parsing rules follow docs/claude-jsonl-schema.md, an empirical reference
built from 58k+ real records. Every read is .get()-guarded; unknown record
types are ignored; a line that fails to parse is counted, never fatal.
"""
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("vibetrace")

CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"
WRITE_TOOLS = {"Edit", "Write", "NotebookEdit"}
PROMPT_CAP = 400
EXCERPT_CAP = 300
MAX_PROMPTS = 20
MAX_EXCERPTS = 12
SYNTHETIC_PREFIXES = ("<", "Stop hook feedback:")


def project_slug(project_path):
    """~/.claude/projects/ dir name: every non-alphanumeric char becomes '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(Path(project_path).resolve()))


def _parse_ts(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError, TypeError):
        return None


def _human_text(obj):
    """Return prompt text if this user record is genuine human input."""
    if obj.get("isMeta") or obj.get("isCompactSummary") or obj.get("isSidechain"):
        return None
    content = (obj.get("message") or {}).get("content")
    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        if any((b or {}).get("type") == "tool_result" for b in content
               if isinstance(b, dict)):
            return None
        text = "\n".join((b or {}).get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text").strip()
    else:
        return None
    if not text or text.startswith(SYNTHETIC_PREFIXES) \
            or text.startswith("[Request interrupted"):
        return None
    return text[:PROMPT_CAP]


def _parse_file(path):
    """Parse one session file into a summary dict. Never raises on bad lines."""
    summary = {
        "session_id": path.stem, "title": "", "start": None, "end": None,
        "prompts": [], "excerpts": [], "files_written": set(),
        "files_read": set(), "records": 0, "parse_failures": 0,
        "tokens": {"input": 0, "output": 0, "cache_read": 0},
    }
    usage_by_msg = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                summary["parse_failures"] += 1
                continue
            if not isinstance(obj, dict):
                summary["parse_failures"] += 1
                continue
            summary["records"] += 1
            rtype = obj.get("type")
            ts = _parse_ts(obj.get("timestamp"))
            if ts:
                summary["start"] = min(summary["start"] or ts, ts)
                summary["end"] = max(summary["end"] or ts, ts)
            if rtype == "ai-title":
                summary["title"] = obj.get("aiTitle") or summary["title"]
            elif rtype == "user":
                sid = obj.get("sessionId")
                if sid:
                    summary["session_id"] = sid
                text = _human_text(obj)
                if text and len(summary["prompts"]) < MAX_PROMPTS:
                    summary["prompts"].append(text)
            elif rtype == "assistant":
                if obj.get("isApiErrorMessage"):
                    continue
                msg = obj.get("message") or {}
                if isinstance(msg.get("usage"), dict):
                    usage_by_msg[msg.get("id") or obj.get("uuid")] = msg["usage"]
                for block in msg.get("content") or []:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "text":
                        text = (block.get("text") or "").strip()
                        if len(text) > 80 and len(summary["excerpts"]) < MAX_EXCERPTS:
                            summary["excerpts"].append(text[:EXCERPT_CAP])
                    elif block.get("type") == "tool_use":
                        inp = block.get("input") or {}
                        target = inp.get("file_path") or inp.get("notebook_path")
                        if not isinstance(target, str):
                            continue
                        if block.get("name") in WRITE_TOOLS:
                            summary["files_written"].add(target)
                        elif block.get("name") == "Read":
                            summary["files_read"].add(target)
    # usage repeats on every streamed line of one message: dedupe by id, then sum
    for usage in usage_by_msg.values():
        summary["tokens"]["input"] += (usage.get("input_tokens") or 0)
        summary["tokens"]["output"] += (usage.get("output_tokens") or 0)
        summary["tokens"]["cache_read"] += (usage.get("cache_read_input_tokens") or 0)
    return summary


def _freeze(summary):
    return {**summary,
            "files_written": sorted(summary["files_written"]),
            "files_read": sorted(summary["files_read"]),
            "start": summary["start"].isoformat() if summary["start"] else None,
            "end": summary["end"].isoformat() if summary["end"] else None}


def _thaw(summary):
    return {**summary,
            "files_written": set(summary["files_written"]),
            "files_read": set(summary["files_read"]),
            "start": _parse_ts(summary["start"]),
            "end": _parse_ts(summary["end"])}


def scan_sessions(project_path, since_dt, cache=None):
    """Return (session summaries, error_or_None). Degrades, never raises.

    Main transcripts only (<sessionId>.jsonl); subagent files are a known
    M0 limitation. With a cache, unchanged files (mtime+size) skip re-parse.
    """
    sessions_dir = CLAUDE_PROJECTS / project_slug(project_path)
    if not sessions_dir.is_dir():
        return [], f"会话目录不存在:{sessions_dir}"
    summaries, failures = [], 0
    for path in sorted(sessions_dir.glob("*.jsonl")):
        try:
            stat = path.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            if since_dt and mtime < since_dt:
                continue  # untouched since before the window
            cached = cache.get_session(path.stem) if cache else None
            if cached and cached["mtime"] == stat.st_mtime \
                    and cached["size"] == stat.st_size:
                summaries.append(_thaw(cached["summary"]))
                continue
            summary = _parse_file(path)
            if summary["parse_failures"]:
                log.warning("%s:%d 行无法解析,已跳过", path.name,
                            summary["parse_failures"])
            if not summary["records"]:
                continue
            summaries.append(summary)
            if cache:
                cache.put_session(path.stem, summary["end"].isoformat()
                                  if summary["end"] else "", stat.st_mtime,
                                  stat.st_size, _freeze(summary))
        except OSError as exc:
            failures += 1
            log.warning("会话文件 %s 读取失败:%s", path.name, exc)
    if not summaries and failures:
        return [], f"全部 {failures} 个会话文件读取失败"
    return summaries, None
