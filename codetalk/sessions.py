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

from .config import redact_secrets

log = logging.getLogger("codetalk")

CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"
WRITE_TOOLS = {"Edit", "Write", "NotebookEdit"}
PROMPT_CAP = 400
EXCERPT_CAP = 1000   # 模型回答通常较长,每条 head_tail 截到 ≤1k(原 300 截太狠);prompt 仍 400
MAX_PROMPTS = 20
MAX_EXCERPTS = 12
SYNTHETIC_PREFIXES = ("<", "Stop hook feedback:")
# 会话信封类型(schema §1.1:仅这 4 类保证带 timestamp);ai-title/last-prompt/leafUuid
# 指针等其余类型天生无 timestamp,不可据此报格式漂移(否则每次正常运行都虚警、钝化信号)。
_ENVELOPE_TYPES = {"user", "assistant", "attachment", "system"}
_format_warned = False


def project_slug(project_path):
    """~/.claude/projects/ dir name: every non-alphanumeric char becomes '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(Path(project_path).resolve()))


def head_tail(value, n):
    """保留首+尾的截断(靠后的话更接近最终决策,纯 head 截断会丢掉它)。
    str → 首 + '…' + 尾,长度不超过 n;list → 首若干 + 尾若干,共 n 个元素。
    未超限原样返回;n<=1 时只留尾。"""
    if len(value) <= n:
        return value
    if isinstance(value, str):
        if n <= 1:
            return value[-n:] if n else ""
        head = n // 2
        tail = n - head - 1          # 留 1 字符给省略号
        return value[:head] + "…" + (value[-tail:] if tail else "")
    if n <= 1:
        return value[-1:]
    head = n // 2
    return value[:head] + value[len(value) - (n - head):]


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
    return redact_secrets(head_tail(text, PROMPT_CAP))  # 保留首尾;入缓存前脱敏


def _parse_file(path, is_subagent=False):
    """Parse one session file into a summary dict. Never raises on bad lines.

    is_subagent marks subagent/sidechain transcripts: their session_id comes
    from the in-record `sessionId` field (the parent session), not the
    filename stem (which is the agentId). Sidechain "user" strings are
    orchestrator briefs, not human intent — already filtered in _human_text —
    but assistant reasoning and tool activity are folded into the summary.
    """
    summary = {
        "session_id": path.stem, "title": "", "start": None, "end": None,
        "prompts": [], "excerpts": [], "files_written": set(),
        "files_read": set(), "records": 0, "parse_failures": 0,
        "is_subagent": is_subagent, "source": "claude",
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
            global _format_warned
            # 格式漂移早警:每条记录都应有 type(普适);信封类还应有 timestamp。仅这两条
            # 触发,避免对天生无 timestamp 的非会话类型(ai-title 等)虚警(round-2 引入的钝化 bug)。
            if not _format_warned and (
                    "type" not in obj
                    or (rtype in _ENVELOPE_TYPES and "timestamp" not in obj)):
                log.warning("Claude Code session format may have changed — record "
                            "lacks expected keys (got %s) in %s. "
                            "Falling back to best-effort parsing.",
                            sorted(obj.keys()), path.name)
                _format_warned = True
            ts = _parse_ts(obj.get("timestamp"))
            if ts:
                summary["start"] = min(summary["start"] or ts, ts)
                summary["end"] = max(summary["end"] or ts, ts)
            if rtype == "ai-title":
                summary["title"] = redact_secrets(obj.get("aiTitle") or "") or summary["title"]
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
                if is_subagent:
                    sid = obj.get("sessionId")  # subagent → parent session id
                    if sid:
                        summary["session_id"] = sid
                msg = obj.get("message") or {}
                if isinstance(msg.get("usage"), dict):
                    usage_by_msg[msg.get("id") or obj.get("uuid")] = msg["usage"]
                for block in msg.get("content") or []:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "text":
                        text = (block.get("text") or "").strip()
                        if len(text) > 80 and len(summary["excerpts"]) < MAX_EXCERPTS:
                            summary["excerpts"].append(
                                redact_secrets(head_tail(text, EXCERPT_CAP)))
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


def _discover(sessions_dir):
    """(path, is_subagent) for every transcript under a project dir.

    Main: <slug>/*.jsonl. Subagent (sidechain): <slug>/<sessionId>/subagents/
    **/agent-*.jsonl — reuses the parent sessionId, carries the user's most
    decision-dense work (superpowers subagents + TDD). journal.jsonl is a
    different schema family and *.meta.json is a sidecar; both excluded.
    Format is non-official: glob defensively, never assume the tree exists.
    """
    files = [(p, False) for p in sorted(sessions_dir.glob("*.jsonl"))]
    for p in sorted(sessions_dir.glob("*/subagents/**/agent-*.jsonl")):
        if p.name == "journal.jsonl" or p.suffix != ".jsonl":
            continue  # belt-and-suspenders: glob already excludes these
        files.append((p, True))
    return files


def scan_sessions(project_path, since_dt, cache=None):
    """Return (session summaries, error_or_None). Degrades, never raises.

    Includes both main transcripts (<sessionId>.jsonl) and subagent/sidechain
    transcripts (folded into the parent session by its `sessionId` field).
    With a cache, unchanged files (mtime+size) skip re-parse.
    """
    sessions_dir = CLAUDE_PROJECTS / project_slug(project_path)
    if not sessions_dir.is_dir():
        return [], f"会话目录不存在:{sessions_dir}"
    summaries, failed_files = [], 0
    for path, is_subagent in _discover(sessions_dir):
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
            summary = _parse_file(path, is_subagent)
            if summary["parse_failures"]:
                log.warning("%s:%d 行无法解析,已跳过", path.name,
                            summary["parse_failures"])
            if not summary["records"]:
                if summary["parse_failures"]:
                    failed_files += 1  # file existed but yielded nothing usable
                continue
            summaries.append(summary)
            if cache:
                cache.put_session(path.stem, summary["end"].isoformat()
                                  if summary["end"] else "", stat.st_mtime,
                                  stat.st_size, _freeze(summary))
        except Exception as exc:  # 容错契约:单文件任何异常都不拖垮 digest
            failed_files += 1
            log.warning("会话文件 %s 处理失败:%r", path.name, exc)
    if not summaries and failed_files:
        return [], f"{failed_files} 个会话文件损坏或不可读"
    return summaries, None
