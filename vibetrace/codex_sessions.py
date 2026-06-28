"""Tolerant parser for OpenAI Codex CLI local sessions → vibetrace session
summaries. Rollout files live at ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl,
one JSON object per line {timestamp,type,payload}; the first line is a
`session_meta` whose payload.cwd gives project attribution. Read-only; every
access guarded; degrades and never raises. Mirrors the cursor_sessions contract
so digest/enrich/prompts merge it without special-casing.
"""
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from .config import VIBETRACE_DIR, redact_secrets
from .sessions import (EXCERPT_CAP, MAX_EXCERPTS, MAX_PROMPTS, PROMPT_CAP,
                       _freeze, _thaw, head_tail)

log = logging.getLogger("vibetrace")

_CODEX_SESSIONS = Path.home() / ".codex" / "sessions"
# apply_patch 信封标记(custom_tool_call/function_call 通用),只取受影响文件【路径】,
# 绝不留补丁正文——正文常含真实 secret(dogfood 实见 OPENAI_API_KEY)。
_PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.M)


def _sessions_dir():
    return _CODEX_SESSIONS


def _ts(value):
    """ISO8601 字符串或 epoch 数字 → tz-aware UTC datetime;非法返回 None。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _text_of(content):
    """message.content(list of {type,text})→ 拼接纯文本;非法→''。"""
    if not isinstance(content, list):
        return ""
    parts = [c["text"] for c in content
             if isinstance(c, dict) and isinstance(c.get("text"), str)]
    return "".join(parts).strip()


def _is_injected(text):
    """Codex 每轮自动注入的 <environment_context>/<user_instructions> 包裹,非真实用户指令。"""
    t = text.lstrip()
    return t.startswith("<environment_context") or t.startswith("<user_instructions")


def _absolutize(paths, root):
    out = set()
    for p in paths:
        pp = Path(p)
        out.add(str(pp if pp.is_absolute() else (root / pp)))
    return out


def _patch_paths(payload):
    """apply_patch 工具调用 → 受影响文件原始路径串(只路径,不含正文)。"""
    blob = payload.get("input") or payload.get("arguments")
    if not isinstance(blob, str) or "*** " not in blob:
        return []
    return [m.strip() for m in _PATCH_FILE.findall(blob)]


def _blank_summary(sid):
    return {"session_id": sid, "title": "", "prompts": [], "excerpts": [],
            "files_written": set(), "files_read": set(),
            "start": None, "end": None, "records": 0, "parse_failures": 0,
            "is_subagent": False,   # 与 Claude/Cursor summary 契约对齐
            "source": "codex",      # evidence 透传:区分原话来自哪个工具
            "tokens": {"input": 0, "output": 0, "cache_read": 0}}


def _peek(path):
    """只读首行 session_meta → (cwd, session_id);快速归属判定,不全量解析。"""
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if isinstance(rec, dict) and rec.get("type") == "session_meta":
                    p = rec.get("payload") or {}
                    return p.get("cwd"), (p.get("session_id") or p.get("id"))
                return None, None        # 首条非 meta → 无法归属
    except (OSError, UnicodeError, ValueError, TypeError):
        return None, None
    return None, None


def _parse_rollout(path):
    """解析单个 rollout → (cwd, summary)。坏行跳过、单文件容错,绝不抛。"""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None, None
    cwd = None
    s = _blank_summary(path.stem)
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except (ValueError, TypeError):
            s["parse_failures"] += 1
            continue
        if not isinstance(rec, dict):
            continue
        payload = rec.get("payload")
        if rec.get("type") == "session_meta" and isinstance(payload, dict):
            cwd = payload.get("cwd")
            sid = payload.get("session_id") or payload.get("id")
            if sid:
                s["session_id"] = sid
            continue
        ts = _ts(rec.get("timestamp"))
        if ts:
            s["start"] = min(s["start"] or ts, ts)
            s["end"] = max(s["end"] or ts, ts)
        if rec.get("type") != "response_item" or not isinstance(payload, dict):
            continue
        ptype = payload.get("type")
        if ptype in ("function_call", "custom_tool_call"):
            root = Path(cwd) if cwd else path.parent
            s["files_written"] |= _absolutize(_patch_paths(payload), root)
            continue
        if ptype != "message":
            continue
        text = _text_of(payload.get("content"))
        if not text:
            continue
        role = payload.get("role")
        if role == "user" and not _is_injected(text):
            s["records"] += 1
            if len(s["prompts"]) < MAX_PROMPTS:
                s["prompts"].append(redact_secrets(head_tail(text, PROMPT_CAP)))
        elif role == "assistant":
            s["records"] += 1
            if len(s["excerpts"]) < MAX_EXCERPTS:
                s["excerpts"].append(redact_secrets(head_tail(text, EXCERPT_CAP)))
    s["title"] = s["prompts"][0][:60] if s["prompts"] else ""
    return cwd, s


def scan_sessions(project_path, since_dt, cache=None):
    """Return (summaries, error_or_None). Degrades, never raises.
    与 sessions.scan_sessions 同契约,供 digest/enrich/prompts 无差别合并。
    归属口径:rollout 的 session_meta.cwd == 项目目录(resolve 相等)。"""
    root = _sessions_dir()
    if not root.is_dir():
        return [], "未找到 Codex 数据目录(未安装或路径不同)"
    target = Path(project_path).resolve()
    try:
        files = sorted(root.rglob("rollout-*.jsonl"))
    except OSError as exc:
        return [], f"Codex 会话目录读失败:{exc}"
    summaries = []
    for fp in files:
        try:
            st = fp.stat()
            if since_dt:   # 早剪枝:rollout 完结后基本不再写,文件 mtime 早于 since 直接跳
                mdt = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
                if mdt < since_dt:
                    continue
            cwd, sid = _peek(fp)
            if not cwd:
                continue
            try:
                if Path(cwd).resolve() != target:   # 仅归属本项目
                    continue
            except (OSError, ValueError):
                continue
            ckey = "codex:" + (sid or fp.stem)      # 源前缀:与 claude/cursor 键隔离
            cached = cache.get_session(ckey) if cache else None
            if cached and cached["mtime"] == st.st_mtime_ns \
                    and cached["size"] == st.st_size:
                s = _thaw(cached["summary"])
            else:
                _cwd, s = _parse_rollout(fp)
                if s is None:
                    continue
                if cache and s["records"]:
                    cache.put_session(
                        ckey, s["end"].isoformat() if s["end"] else "",
                        st.st_mtime_ns, st.st_size, _freeze(s))
            if not s["records"]:
                continue
            if since_dt and s["end"] and s["end"] < since_dt:
                continue
            summaries.append(s)
        except Exception as exc:   # 单会话容错,不拖垮整体
            log.warning("Codex 会话 %s 解析失败:%r", fp.name, exc)
    return summaries, None


NOTICE_SENTINEL = VIBETRACE_DIR / ".codex_notice_shown"


def maybe_notice():
    """首次启用 Codex 源时一次性告知(本地只读、可关),之后静默。"""
    try:
        if NOTICE_SENTINEL.exists():
            return
        log.warning("已启用 Codex 会话源:将读取本地 Codex rollout 会话(只读、不出本机);"
                    "可在 ~/.vibetrace/config.json 的 sources 移除 \"codex\" 关闭。")
        NOTICE_SENTINEL.parent.mkdir(parents=True, exist_ok=True)
        NOTICE_SENTINEL.write_text("", encoding="utf-8")
    except OSError:
        pass   # sentinel 写不了也不能拖垮主流程
